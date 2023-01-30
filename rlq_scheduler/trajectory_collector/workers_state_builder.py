import time
from copy import deepcopy
from threading import Thread, Event, RLock

from rlq_scheduler.common.backends.base_backend import BaseBackend
from rlq_scheduler.common.config_helper import GlobalConfigHelper, TrajectoryCollectorConfigHelper, RunConfigHelper
from rlq_scheduler.common.exceptions import CeleryNotReachable
from rlq_scheduler.common.system_events.producer import SystemEventProducer
from rlq_scheduler.common.system_status import ResourceStatus
from rlq_scheduler.common.utils.logger import get_logger
from rlq_scheduler.common.state.state_builder import StateBuilder


class WorkersStateBuilder:

    def __init__(self,
                 celery_app,
                 backend: BaseBackend,
                 config: TrajectoryCollectorConfigHelper,
                 global_config: GlobalConfigHelper,
                 system_producer: SystemEventProducer,
                 state_builder: StateBuilder,
                 logger=None):
        self.logger = logger if logger is not None else get_logger(self.config.logger())
        self.config = config
        self.run_config: RunConfigHelper = None
        self.global_config = global_config
        self.celery_app = celery_app
        self.backend: BaseBackend = backend
        self.system_producer: SystemEventProducer = system_producer
        self.state_builder: StateBuilder = state_builder
        self.pool_info = {
            'pool_total': 0,
            'workers': {}
        }
        self.pool_info_next = {
            'pool_total': 0,
            'workers': {}
        }
        self.name = 'WorkersStateBuilder'
        self.stop_event = Event()
        self.resource_lock = RLock()
        self.workers_state_builder_thread = None
        self.workers_ping_thread = None
        self.is_ready = False
        self.is_running = False

    def init_threads(self):
        self.workers_state_builder_thread = Thread(name=self.name + '-main', target=self._do_workers_state)
        self.workers_ping_thread = Thread(name=self.name + '-ping', target=self._do_check_workers_available)

    def env_status(self, retry=0, max_retries=5):
        if retry > max_retries:
            raise CeleryNotReachable
        self.logger.info('Gathering initial worker status, retry = {}'.format(retry), resource='WorkersStateBuilder')
        inspection = self.celery_app.control.inspect()
        ping = inspection.ping()
        if ping is None:
            self.logger.info('Celery is not reachable. Retrying in {} seconds'.format(10 * retry),
                             resource='WorkersStateBuilder')
            time.sleep(10 * retry)
            self.env_status(retry + 1, max_retries)
        active_queues = inspection.active_queues()
        if len(ping) != len(active_queues):
            self.logger.info('Celery is not reachable. Retrying in {} seconds'.format(10 * retry),
                             resource='WorkersStateBuilder')
            time.sleep(10 * retry)
            self.env_status(retry + 1, max_retries)
        for worker_fullname, info in ping.items():
            worker = GlobalConfigHelper.get_worker_class_from_fullname(worker_fullname)
            self.logger.info('Worker: {} ping response: {}'.format(worker, info), resource='WorkersStateBuilder')
            worker_queues = active_queues[worker_fullname]
            self.logger.info('Worker: {} active queues: {}'
                             .format(worker, ', '.join([queue_info['name'] for queue_info in worker_queues])),
                             resource='WorkersStateBuilder')
            if info['ok'] == 'pong':
                if worker != self.global_config.task_broker_worker_name():
                    if worker in self.pool_info['workers']:
                        self.pool_info['workers'][worker]['total_workers'] += 1
                        self.pool_info['workers'][worker]['available_workers'] += 1
                    else:
                        self.pool_info['workers'][worker] = {
                            'total_workers': 1,
                            'available_workers': 1,
                            'queued': 0
                        }
                    self.pool_info['pool_total'] += 1
        self.pool_info_next = deepcopy(self.pool_info)
        if len(self.pool_info['workers']) != len(self.global_config.available_worker_classes()):
            self.logger.warning('Some worker queues are not available, pool info = {}, required queues = {}'
                                .format(self.pool_info, self.global_config.available_worker_classes()),
                                resource='WorkersStateBuilder')
        else:
            self.logger.info('Pool info = {}'.format(self.pool_info), resource='WorkersStateBuilder')

    def start(self):
        try:
            if self.is_running is False:
                self.init_threads()
                self.env_status()
                self.logger.info(f'{self.name} is starting to build workers state', resource='WorkersStateBuilder')
                self.workers_state_builder_thread.start()
                self.workers_ping_thread.start()
                self.is_running = True
        except Exception as e:
            self.logger.exception(e)
            self.system_producer.publish_resource_status_changed_event(
                resource_name='trajectory_collector',
                status=ResourceStatus.ERROR
            )

    def stop(self):
        self.logger.info(f'{self.name} is going to stop its execution', resource='WorkersStateBuilder')
        self.stop_event.set()
        self.workers_state_builder_thread.join(timeout=5)
        self.workers_ping_thread.join(timeout=5)
        self.is_ready = False
        self.is_running = False
        self.workers_state_builder_thread = None
        self.workers_ping_thread = None
        self.stop_event.clear()
        self.logger.info(f'{self.name} has released all the resources', resource='WorkersStateBuilder')

    def _do_workers_state(self):
        try:
            self.logger.debug('workers_state_builder_thread is starting', resource='WorkersStateBuilder')
            while not self.stop_event.is_set():
                self._update_worker_state()
                time.sleep(self.config.worker_state_update_interval())
            self.logger.debug('workers_state_builder_thread has been stopped', resource='WorkersStateBuilder')
        except Exception as e:
            self.logger.exception(e)

    def _do_check_workers_available(self):
        try:
            self.logger.debug('workers_ping_thread is starting', resource='WorkersStateBuilder')
            while not self.stop_event.is_set():
                self._ping_workers()
                time.sleep(self.config.worker_state_workers_ping_interval())
            self.logger.debug('workers_ping_thread has been stopped', resource='WorkersStateBuilder')
        except Exception as e:
            self.logger.exception(e)

    def _update_worker_state(self):
        self.pool_info = deepcopy(self.pool_info_next)
        inspection = self.celery_app.control.inspect()
        tasks_executing = inspection.active()
        reserved_tasks = inspection.reserved()
        self._update_pool_info(tasks_executing, reserved_tasks)
        self._update_state_builder_pool_info()

    def _update_pool_info(self, tasks_executing, reserved_tasks):
        with self.resource_lock:
            for worker_class, class_info in self.pool_info['workers'].items():
                class_info['available_workers'] = class_info['total_workers']
        for worker_fullname, tasks_in_executions in tasks_executing.items():
            worker = GlobalConfigHelper.get_worker_class_from_fullname(worker_fullname)
            with self.resource_lock:
                if worker in self.pool_info['workers'] and worker_fullname in tasks_executing \
                        and worker_fullname in reserved_tasks:
                    self.pool_info['workers'][worker]['queued'] = len(reserved_tasks[worker_fullname])
                    if len(tasks_in_executions) > 0:
                        self.pool_info['workers'][worker]['available_workers'] -= 1
        with self.resource_lock:
            self.logger.debug('Updated pool info = {}'.format(self.pool_info), resource='WorkersStateBuilder')

    def _update_state_builder_pool_info(self):
        result = self.state_builder.update_pool_info(self.pool_info)
        if result is True:
            if self.is_ready is False:
                self.is_ready = True
                time.sleep(0.2)
                self.system_producer.publish_resource_status_changed_event(
                    resource_name='trajectory_collector',
                    status=ResourceStatus.READY
                )
            self.logger.debug('Updated workers state features', resource='WorkersStateBuilder')
        else:
            self.logger.error('Error while saving workers state features', resource='WorkersStateBuilder')

    def _ping_workers(self):
        inspection = self.celery_app.control.inspect()
        ping = inspection.ping()
        tmp_worker_pool_info = {
            'pool_total': 0,
            'workers': {}
        }
        for worker, worker_info in self.pool_info_next['workers'].items():
            tmp_worker_pool_info['workers'][worker] = {
                'total_workers': 0,
                'available_workers': 0,
                'queued': 0
            }
        self.logger.debug('Ping = {}'.format(ping), resource='WorkersStateBuilder')
        for worker_fullname, info in ping.items():
            worker = GlobalConfigHelper.get_worker_class_from_fullname(worker_fullname)
            if info['ok'] == 'pong':
                if worker != self.global_config.task_broker_worker_name():
                    if worker in self.pool_info_next['workers']:
                        available_workers = self.pool_info_next['workers'][worker]['available_workers']
                        queued_tasks = self.pool_info_next['workers'][worker]['queued']
                    else:
                        available_workers = 0
                        queued_tasks = 0
                    if worker in tmp_worker_pool_info['workers']:
                        tmp_worker_pool_info['workers'][worker]['total_workers'] += 1
                        tmp_worker_pool_info['workers'][worker]['available_workers'] = available_workers
                    else:
                        tmp_worker_pool_info['workers'][worker] = {
                            'total_workers': 1,
                            'available_workers': available_workers,
                            'queued': queued_tasks
                        }
                    tmp_worker_pool_info['pool_total'] += 1
        with self.resource_lock:
            if self.pool_info_next['pool_total'] != tmp_worker_pool_info['pool_total']:
                self.logger.info('The total number of workers reachable is changed. Before was {} now is {}'
                                 .format(self.pool_info_next['pool_total'], tmp_worker_pool_info['pool_total']),
                                 resource='WorkersStateBuilder')
                self.pool_info_next = deepcopy(tmp_worker_pool_info)
