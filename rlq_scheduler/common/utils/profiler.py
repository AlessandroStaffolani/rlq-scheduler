import functools
import os
import random
import string
import time
import numpy as np
from threading import Thread, Event

import psutil

from rlq_scheduler.common.utils.logger import get_logger

LOGGER_CONFIG = {
    'name': 'profiler',
    'level': 20,
    'handlers': [
        {'type': 'console', 'parameters': None}
    ]
}


def format_timestamp(t):
    milliseconds = t - int(t)
    milliseconds = str(round(milliseconds, 3))[1:]
    return time.strftime("%H:%M:%S", time.gmtime(t)) + milliseconds


def get_elapsed_time(start: float, end: float):
    return format_timestamp(end - start)


def random_id(length=8):
    alphabet = string.ascii_letters + string.digits
    return ''.join(random.choices(alphabet, k=length))


class ProcessMetrics:

    def __init__(self, pid, name, metrics, metrics_type=None):
        self.pid = pid
        self.name = name
        self.numerical_metrics_keys = metrics
        self.numerical_metrics_types = metrics_type
        self.metrics = {m: 0 for m in self.numerical_metrics_keys}
        self.metrics_history = {m: [] for m in self.numerical_metrics_keys}
        self.metrics['start_time'] = None
        self.metrics['end_time'] = None
        self.metrics['elapsed_time'] = None

    def __getitem__(self, item):
        return self.metrics[item]

    def __setitem__(self, key, value):
        self.metrics[key] = value
        self.metrics_history[key].append(value)

    def set_metrics(self, **kwargs):
        for metric, value in kwargs.items():
            self.metrics[metric] = value
            if metric in self.metrics_history:
                self.metrics_history[metric].append(value)

    def numerical_metrics(self):
        return {metric: value for metric, value in self.metrics.items() if metric in self.numerical_metrics_keys}

    def keys(self):
        return self.metrics.keys()

    def numerical_metrics_keys(self):
        return self.numerical_metrics_keys

    def items(self):
        return self.metrics.items()

    def numerical_metrics_items(self):
        return self.numerical_metrics().items()

    def history_items(self):
        return self.metrics_history.items()

    def values(self):
        return self.metrics.values()

    def numerical_metrics_values(self):
        return self.numerical_metrics().values()

    def history_values(self):
        return self.metrics_history.values()

    def average(self):
        m_history_numpy = {metric: np.array(values) for metric, values in self.history_items()}
        return {metric: value.mean() for metric, value in m_history_numpy.items()}

    def __str__(self):
        return '<ProcessMetrics pid={} name={} metrics={} >'.format(self.pid, self.name, self.numerical_metrics_keys)

    def _format_value(self, metric, value):
        if self.numerical_metrics_types is not None and metric in self.numerical_metrics_types:
            m_type = self.numerical_metrics_types[metric]
            if m_type == 'mb':
                value = value / (1024 * 1024)
            return f'{str(round(value, 4))}{m_type}'
        elif value is not None and not isinstance(value, str):
            return str(round(value, 2))
        else:
            return str(value)

    def metrics_to_string(self):
        value_string = f'Process: pid={self.pid} name={self.name} | metrics:'
        for metric, value in self.items():
            value_string += f' {metric}={self._format_value(metric, value)} -'
        return value_string[:-1]

    def average_to_string(self):
        value_string = f'Process: pid={self.pid} name={self.name} | average metrics:'
        for metric, value in self.average().items():
            value_string += f' {metric}={self._format_value(metric, value)} -'
        value_string += f' duration={self.metrics["elapsed_time"]}'
        return value_string


class Profiler(Thread):

    def __init__(self, process: psutil.Process, name=None, start_time=None, interval=2.0):
        super(Profiler, self).__init__(name='MonitorThread')
        self.logger = get_logger(LOGGER_CONFIG)
        self.process = process
        self.process_name = name
        self.process_pid = process.pid
        self.interval = interval
        self.start_time = start_time
        self.end_time = None
        self.stop = Event()
        self.current_process_metrics = ProcessMetrics(
            pid=self.process.pid,
            name=self.process_name,
            metrics=['cpu_perc', 'process_ram', 'process_ram_perc', 'swap', 'swap_perc'],
            metrics_type={'cpu_perc': '%', 'process_ram': 'mb', 'process_ram_perc': '%', 'swap': 'mb', 'swap_perc': '%'}
        )

    def update_process_metrics(self, cpu_interval=None, is_first=False):
        with self.process.oneshot():
            cpu_perc = self.process.cpu_percent(interval=cpu_interval)
            memory_full_info = self.process.memory_full_info()
            process_ram = memory_full_info.uss
            process_ram_perc = self.process.memory_percent(memtype='uss')
            if 'swap' in memory_full_info._fields:
                swap = memory_full_info.swap
                swap_perc = self.process.memory_percent('swap')
            else:
                swap = 0
                swap_perc = 0
        if self.end_time is not None:
            elapsed_time = get_elapsed_time(self.start_time, self.end_time)
        else:
            elapsed_time = get_elapsed_time(self.start_time, time.time())
        if is_first is False:
            metrics = {
                'start_time': self.start_time,
                'cpu_perc': cpu_perc,
                'process_ram': process_ram,
                'process_ram_perc': process_ram_perc,
                'swap': swap,
                'swap_perc': swap_perc,
                'end_time': self.end_time,
                'elapsed_time': elapsed_time
            }
            self.current_process_metrics.set_metrics(**metrics)
            self.logger.debug('Updated metrics with values: {}'.format(metrics))

    def log_metrics(self):
        self.logger.info(self.current_process_metrics.metrics_to_string())

    def show_profiling_metrics(self):
        self.log_metrics()

    def start_profiling_metrics_message(self):
        message = f'Starting profiling | id: {self.process_pid}'
        if self.process_name is not None:
            message += f' | name: {self.process_name}'
        self.logger.info(message)

    def stop_profiling_metrics_message(self):
        # self.update_process_metrics()
        message = f'Stopping profiling | {self.current_process_metrics.average_to_string()}'
        self.logger.info(message)

    def run(self) -> None:
        if self.start_time is None:
            raise AttributeError('Start_time is None')
        self.start_profiling_metrics_message()
        self.update_process_metrics(cpu_interval=0, is_first=True)
        while not self.stop.is_set():
            time.sleep(self.interval)
            if not self.stop.is_set():
                self.update_process_metrics(cpu_interval=None)
                self.show_profiling_metrics()
        self.stop_profiling_metrics_message()

    @staticmethod
    def _format_time(t):
        return time.strftime("%H:%M:%S", time.gmtime(t))

    @staticmethod
    def _get_process_memory_info(p: psutil.Process):
        return p.memory_info().rss / 10 ** 6, p.memory_percent()

    @staticmethod
    def _get_process_cpu(p: psutil.Process):
        return p.cpu_percent()

    @staticmethod
    def _get_elapsed_time(start: float, end: float):
        return time.strftime("%H:%M:%S", time.gmtime(end - start))


def profile(interval=1):
    def decorator_profiler(func):
        @functools.wraps(func)
        def wrapper_profiler(*args, **kwargs):
            process: psutil.Process = psutil.Process(os.getpid())
            start = time.time()
            profiler = Profiler(process, name=func.__name__, start_time=start, interval=interval)
            try:
                profiler.start()
                value = func(*args, **kwargs)
                profiler.end_time = time.time()
                profiler.stop.set()
                profiler.join(timeout=interval + 1)
                return value
            except Exception as e:
                profiler.end_time = time.time()
                profiler.stop.set()
                profiler.join(timeout=interval + 1)
                raise e

        return wrapper_profiler

    return decorator_profiler
