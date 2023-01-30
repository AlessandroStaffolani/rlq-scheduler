import ast
import json
from threading import Thread, Lock, Event as ThreadEvent
from multiprocessing.pool import ThreadPool

import redis.exceptions
from celery import Celery
from celery.events.state import State

from rlq_scheduler.common.backends.base_backend import BaseTrajectoryBackend
from rlq_scheduler.common.config_helper import GlobalConfigHelper, TrajectoryCollectorConfigHelper, \
    ExecutionTimeMode, RunConfigHelper
from rlq_scheduler.common.distributed_queue.base_queue import BaseDistributedQueue
from rlq_scheduler.common.distributed_queue.queue_factory import get_distributed_queue
from rlq_scheduler.common.state.state_builder import StateBuilder
from rlq_scheduler.common.utils.celery_utils import get_task_uuid_from_full_task_id
from rlq_scheduler.common.utils.logger import get_logger
from rlq_scheduler.trajectory_collector.consumer.event import Event, EventType


class Consumer(Thread):

    def __init__(self,
                 celery_app: Celery,
                 trajectory_backend: BaseTrajectoryBackend,
                 config: TrajectoryCollectorConfigHelper,
                 global_config: GlobalConfigHelper,
                 state_builder: StateBuilder,
                 workers_load_updated_event: ThreadEvent,
                 async_worker: ThreadPool,
                 logger=None):
        super(Consumer, self).__init__(name='ConsumerThread')
        self.config = config
        self.global_config = global_config
        self.run_config: RunConfigHelper = None
        self.celery_app = celery_app
        self.logger = logger if logger is not None else get_logger(self.config.logger())
        self.celery_app_state: State = celery_app.events.State(max_tasks_in_memory=50000)
        queue_class = get_distributed_queue(self.config.consumer_queue_type())
        self.queue: BaseDistributedQueue = queue_class(self.config.consumer_queue_config())
        self.trajectory_backend: BaseTrajectoryBackend = trajectory_backend
        self.receiver = None
        self.is_ready = False
        self.threading_lock = Lock()
        self.state_builder: StateBuilder = state_builder
        self.workers_load_updated_event: ThreadEvent = workers_load_updated_event
        self.async_worker: ThreadPool = async_worker

    def _trigger_state_creation(self, task_uuid, task_class, timestamp):
        data = json.dumps({'task_uuid': task_uuid, 'task_class': task_class, 'timestamp': timestamp})
        self.logger.debug('pushing to trajectory_builder a state creation event with payload: {}'.format(data),
                          resource='Consumer')
        self.queue.push(self.config.consumer_queue_state_creation_key(), data, push_if_not_present=True)

    def _trigger_reward_computation(self, task_uuid, task_class, runtime, worker_class, failed=False):
        data = json.dumps({'task_uuid': task_uuid,
                           'task_class': task_class,
                           'runtime': runtime,
                           'worker_class': worker_class,
                           'failed': failed})
        self.queue.push(self.config.consumer_queue_compute_reward_key(), data, push_if_not_present=True)

    def _create_task_waiting_time_entry(self, task_uuid, timestamp):
        if self.run_config is not None and self.run_config.is_waiting_time_enabled() is True:
            with self.threading_lock:
                task_waiting_time = self.trajectory_backend.get_task_waiting_time(task_uuid)
                if task_waiting_time is None:
                    res = self.trajectory_backend.set_task_waiting_time(task_uuid, started=timestamp)
                    if res is True:
                        self.logger.debug('Task waiting time created for task {}'.format(task_uuid),
                                          resource='Consumer')
                    else:
                        self.logger.warning('Some errors occurred while creating task waiting time for task {}'
                                            .format(task_uuid), resource='Consumer')
                else:
                    self.logger.debug('Task waiting time is not None for task {}'.format(task_uuid),
                                      resource='Consumer')

    def _compute_task_waiting_time(self, task_uuid, timestamp):
        if self.run_config is not None and self.run_config.is_waiting_time_enabled():
            with self.threading_lock:
                waiting_struct = self.trajectory_backend.get_task_waiting_time(task_uuid)
                self.logger.debug(
                    'Computing waiting time for task {}, start time is {}'.format(task_uuid, waiting_struct),
                    resource='Consumer')
                if waiting_struct is None:
                    waiting_struct = {
                        'started': timestamp,
                        'waited': None
                    }
                started = waiting_struct['started']
                waiting_time = timestamp - started
        else:
            started = timestamp
            waiting_time = 0
        with self.threading_lock:
            self.trajectory_backend.set_task_waiting_time(task_uuid, started=started, waited=waiting_time)
            self.logger.debug('Task {} waiting time is {}'.format(task_uuid, waiting_time), resource='Consumer')

    def _update_workers_state_features(self, worker_class: str, task_to_add: int,
                                       task_class: str, task_parameters: dict):
        if self.run_config is not None:
            with self.threading_lock:
                self.state_builder.update_pool_load(worker_class, load_update=task_to_add,
                                                    task_class=task_class, task_parameters=task_parameters)
                self.logger.debug('Updated workers pool load feature', resource='Consumer')
                self.workers_load_updated_event.set()
            self.async_worker.apply_async(
                func=self.state_builder.upload_pool_load_on_shared_memory,
                error_callback=lambda e: self.logger.exception(e)
            )
        else:
            self.logger.error('No run_config while trying to update workers state features', resource='Consumer')

    def stop(self):
        self.logger.info('Stopping consumer', resource='Consumer')
        if self.receiver is not None:
            self.receiver.should_stop = True

    def run(self) -> None:
        try:
            self.logger.info('Starting event consumer', resource='Consumer')
            self._run()
        except Exception as e:
            self.logger.exception(e)

    def _run(self, retry=0, previous_exception=None):
        if retry > 5:
            self.logger.error('Consumer run failed 5 times')
            raise previous_exception
        try:
            if retry > 0:
                self.logger.warning(f'Consumer connection failed, retry number {retry}')
            with self.celery_app.connection_for_read() as connection:
                self.receiver = self.celery_app.events.Receiver(connection, handlers={
                    'task-sent': self._on_task_sent,
                    'task-received': self._on_task_received,
                    'task-succeeded': self._on_task_succeeded,
                    'task-failed': self._on_task_failed,
                    '*': self.celery_app_state.event
                })
                self.is_ready = True
                self.receiver.capture(limit=None, timeout=None, wakeup=True)
        except redis.exceptions.ConnectionError as e:
            self._run(retry + 1, e)

    def _on_task_event(self, event):
        self.celery_app_state.event(event)
        task = self.celery_app_state.tasks.get(event['uuid'])
        if task.name is None and '.exec' in event['uuid']:
            original_task = self.celery_app_state.tasks.get(event['uuid'].replace('.exec', ''))
            self.logger.warning(f'task {event["uuid"]} not found, original task is: {original_task} |'
                                f' original task_name = {original_task.name if original_task is not None else "None"} |'
                                f' original task_info = {original_task.info() if original_task is not None else "{}"}')
        return task

    def _on_task_sent(self, event):
        task = self._on_task_event(event)
        if not self._filter_taskbroker_tasks_using_queue(event['queue']):
            # I'm going to process only events coming from the a queue different from the TaskBroker Queue
            message = Event('Task: {}[{}] sent on queue {}'
                            .format(task.name,
                                    task.uuid,
                                    event['queue']),
                            EventType.TASK_SENT,
                            timestamp=event['timestamp'],
                            task_name=task.name,
                            task=task_to_json(task)
                            )
            self.logger.info(message.log_str(long=True), resource='Consumer')

            # update workers state features
            worker_class = event['queue']
            task_info = task.info()
            task_class = self._get_task_class_from_task_info(task_info)
            task_parameters = self._get_task_parameters_from_task_info(task_info)
            self._update_workers_state_features(worker_class, task_to_add=1,
                                                task_class=task_class, task_parameters=task_parameters)

            task_uuid = get_task_uuid_from_full_task_id(task.uuid)
            self._create_task_waiting_time_entry(task_uuid, event['timestamp'])

    def _on_task_received(self, event):
        task = self._on_task_event(event)
        self.logger.debug('Event received: {} | task_uuid: {}'.format(event, task.uuid), resource='Consumer')
        if self._filter_taskbroker_tasks(task.name, event['hostname'], event):
            # I'm going to process only events fired by the TaskBroker
            message = Event('Task: {}[{}] received by hostname: {}'.format(task.name, task.uuid, event['hostname']),
                            EventType.TASK_RECEIVED_TASK_BROKER,
                            worker_name=event['hostname'],
                            task_name=task.name,
                            task=task_to_json(task)
                            )
            self.logger.info(message.log_str(long=True), resource='Consumer')
            # ask to build the state of the environment
            self._trigger_state_creation(task_uuid=task.uuid,
                                         task_class=self._get_task_class_from_task_broker_task_info(task.info()),
                                         timestamp=event['timestamp'])
        else:
            # I'm going to process only events fired by workers different from the TaskBroker
            message = Event('Task: {}[{}] received by hostname: {}'
                            .format(task.name, task.uuid, event['hostname']),
                            EventType.TASK_RECEIVED_WORKER,
                            worker_name=event['hostname'],
                            timestamp=event['timestamp'],
                            task_name=task.name,
                            task=task_to_json(task)
                            )
            self.logger.info(message.log_str(long=True), resource='Consumer')
            task_uuid = get_task_uuid_from_full_task_id(task.uuid)
            self._compute_task_waiting_time(task_uuid, event['timestamp'])

    def _on_task_succeeded(self, event):
        task = self._on_task_event(event)
        if not self._filter_taskbroker_tasks(task.name, event['hostname'], event):
            # I'm going to process only events fired by workers different from the TaskBroker
            message = Event('Task: {}[{}] completed in {} seconds by hostname: {}'
                            .format(task.name, task.uuid, event['runtime'], event['hostname']),
                            EventType.TASK_SUCCEEDED,
                            runtime=event['runtime'],
                            worker_name=event['hostname'],
                            task_name=task.name,
                            task=task_to_json(task)
                            )
            self.logger.info(message.log_str(long=True), resource='Consumer')
            worker_class = GlobalConfigHelper.get_worker_class_from_fullname(event['hostname'])

            execution_time = event['runtime']
            if self.run_config.execution_time_mode() == ExecutionTimeMode.EVENT:
                execution_time = event['runtime']
            elif self.run_config.execution_time_mode() == ExecutionTimeMode.RESULT:
                execution_time = float(event['result'])

            # update workers state features
            task_info = task.info()
            task_class = self._get_task_class_from_task_info(task_info, event)
            task_parameters = self._get_task_parameters_from_task_info(task_info, event)
            self._update_workers_state_features(worker_class, task_to_add=-1,
                                                task_class=task_class, task_parameters=task_parameters)

            task_uuid = get_task_uuid_from_full_task_id(task.uuid)
            self._trigger_reward_computation(task_uuid, task_class, execution_time, worker_class, failed=False)

    def _on_task_failed(self, event):
        task = self._on_task_event(event)
        if not self._filter_taskbroker_tasks(task.name, event['hostname'], event):
            # I'm going to process only events fired by workers different from the TaskBroker
            message = Event('Task: {}[{}] failed on hostname: {}'
                            .format(task.name, task.uuid, event['hostname']),
                            EventType.TASK_FAILED,
                            worker_name=event['hostname'],
                            timestamp=event['timestamp'],
                            task_name=task.name,
                            task=task_to_json(task)
                            )
            self.logger.info(message.log_str(long=True), resource='Consumer')
            task_uuid = get_task_uuid_from_full_task_id(task.uuid)
            worker_class = GlobalConfigHelper.get_worker_class_from_fullname(event['hostname'])
            task_class = self._get_task_class_from_task_info(task.info())
            execution_time = None
            # update workers state features
            task_info = task.info()
            task_class = self._get_task_class_from_task_info(task_info)
            task_parameters = self._get_task_parameters_from_task_info(task_info)
            self._update_workers_state_features(worker_class, task_to_add=-1,
                                                task_class=task_class, task_parameters=task_parameters)

            self._trigger_reward_computation(task_uuid, task_class, execution_time, worker_class, failed=True)

    def _filter_taskbroker_tasks(self, task_name, worker_name, event=None):
        if task_name is None:
            self.logger.warning('in _filter_taskbroker_tasks task_name is None when it should not, '
                                'trying to recover information from assigment entry')
            task_name = self._get_task_name_from_assignment_entry(event['uuid'])
        if self.global_config.task_broker_task_name() in task_name \
                and self.global_config.task_broker_worker_name() in worker_name:
            return True
        else:
            return False

    def _get_task_name_from_assignment_entry(self, task_id):
        key = f'{self.global_config.backend_assignment_entry_prefix()}_{task_id.replace(".exec", "")}'
        result = self.trajectory_backend.redis_connection.get(key)
        if result is not None:
            assignment_entry = json.loads(result.decode('utf-8'))
            return assignment_entry['task_name']
        else:
            raise Exception(f'task_id: {task_id} got lost')

    def _get_task_params_from_assignment_entry(self, task_id):
        key = f'{self.global_config.backend_assignment_entry_prefix()}_{task_id.replace(".exec", "")}'
        result = self.trajectory_backend.redis_connection.get(key)
        if result is not None:
            assignment_entry = json.loads(result.decode('utf-8'))
            return assignment_entry['task_params']
        else:
            raise Exception(f'task_id: {task_id} got lost')

    def _filter_taskbroker_tasks_using_queue(self, queue):
        return self.global_config.task_broker_queue_name() == queue

    def _get_task_class_from_task_broker_task_info(self, task_info):
        kwargs = ast.literal_eval(task_info['kwargs'])
        task_parameters = kwargs['parameters']
        task_class = task_parameters['task_class']
        return task_class

    def _get_task_parameters_from_task_info(self, task_info, event=None):
        if 'kwargs' not in task_info or task_info is None:
            self.logger.warning('in _get_task_parameters_from_task_info task_info is None when it should not, '
                                'trying to recover information from assigment entry')
            return self._get_task_params_from_assignment_entry(event['uuid'])
        try:
            kwargs = ast.literal_eval(task_info['kwargs'])
            return kwargs
        except Exception as e:
            self.logger.error(f'error while fetching task parameters | task_info = {task_info}')
            raise e

    def _get_task_class_from_task_info(self, task_info, event=None):
        if 'kwargs' not in task_info or task_info is None:
            self.logger.warning('in _get_task_class_from_task_info task_info is None when it should not, '
                                'trying to recover information from assigment entry')
            return self._get_task_name_from_assignment_entry(event['uuid'])
        try:
            kwargs = ast.literal_eval(task_info['kwargs'])
            return kwargs['task_class']
        except Exception as e:
            self.logger.error(f'error while fetching task parameters | task_info = {task_info}')
            raise e


def task_to_json(task):
    data = {
        'task': {
            'name': task.name,
            'uuid': task.uuid,
            'info': task.info()
        }
    }
    return json.dumps(data)
