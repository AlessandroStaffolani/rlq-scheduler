from __future__ import absolute_import, unicode_literals, division, print_function

import os
import time
from logging import Logger

import numpy as np
from celery.utils.log import get_task_logger

from rlq_scheduler.celery_app import app
from rlq_scheduler.common.config_helper import GlobalConfigHelper
from rlq_scheduler.common.utils.filesystem import create_directory_from_filepath

logger: Logger = get_task_logger(__name__)

global_config: GlobalConfigHelper = GlobalConfigHelper(config_path='config/global.yml')

MEGABYTE = 1024 * 1024


"""
Tasks used for the Synthetic Workload Evaluation:
    - cpu_task
    - disk_task
    - ram_and_cpu_task
    - disk_and_computation_task
Tasks used for the Real-World Workload Evaluation:
    - google_trace_task
"""


@app.task(retry_kwargs={'max_retries': 0})
def cpu_task(n, d, **kwargs):
    start = time.time()
    for i in range(n):
        m = np.random.random((d, d))
        tmp = np.linalg.inv(m) @ np.transpose(m)
        np.linalg.matrix_power(tmp, i)
    time_execution = time.time() - start
    return time_execution


@app.task(retry_kwargs={'max_retries': 0})
def ram_and_cpu_task(n, d, **kwargs):
    matrices = []
    previous = None
    start = time.time()
    for i in range(n + 1):
        m = np.random.random((d, d))
        if previous is not None:
            tmp = np.linalg.inv(m) @ np.transpose(m)
            tmp = np.linalg.matrix_power(tmp, i)
            matrices.append(tmp)
        previous = m
    time_execution = time.time() - start
    return time_execution


@app.task(retry_kwargs={'max_retries': 0})
def disk_task(n, **kwargs):
    filename = '/opt/service-broker/worker/data/file.txt'
    create_directory_from_filepath(filename)
    start = time.time()
    try:
        for i in range(n):
            with open(filename, 'a') as file:
                mega_str = 'A' * MEGABYTE
                file.write(mega_str + '\n')
            with open(filename) as file:
                for _ in file:
                    pass
        time_execution = time.time() - start
        os.remove(filename)
        return time_execution
    except OSError as e:
        os.remove(filename)
        raise e


@app.task(retry_kwargs={'max_retries': 0})
def disk_and_computation_task(n, d, **kwargs):
    filename = '/opt/service-broker/worker/data/file.txt'
    create_directory_from_filepath(filename)
    start = time.time()
    for i in range(n):
        with open(filename, 'a') as file:
            m = np.random.random((d, d))
            tmp = np.linalg.inv(m) @ np.transpose(m)
            tmp = np.linalg.matrix_power(tmp, i)
            file.write(str(tmp.tolist()) + '\n')
    time_execution = time.time() - start
    os.remove(filename)
    return time_execution


@app.task(retry_kwargs={'max_retries': 0})
def google_trace_task(time_of_execution, **kwargs):
    speed_factor = global_config.worker_class_speed_factor(os.getenv('WORKER_NAME'))
    final_execution_time = time_of_execution / speed_factor
    time.sleep(final_execution_time)
    return final_execution_time

