import json
from threading import Lock, Event
from multiprocessing.pool import ThreadPool

from rlq_scheduler.common.backends.base_backend import BaseTrajectoryBackend, BaseBackend
from rlq_scheduler.common.config_helper import GlobalConfigHelper, TrajectoryCollectorConfigHelper, RunConfigHelper
from rlq_scheduler.common.cost_function import ExecutionCostCalculator
from rlq_scheduler.common.distributed_queue.base_queue import BaseDistributedQueue
from rlq_scheduler.common.reward_function import BaseRewardFunction
from rlq_scheduler.common.state.state import Features
from rlq_scheduler.common.stats import StatsBackend
from rlq_scheduler.common.system_events.event import RunPhase
from rlq_scheduler.common.system_events.producer import SystemEventProducer
from rlq_scheduler.common.system_status import ResourceStatus
from rlq_scheduler.common.trajectory import Trajectory, TrajectoryProperties
from rlq_scheduler.common.trajectory_saver.saver import Saver
from rlq_scheduler.common.utils.logger import get_logger
from rlq_scheduler.common.state.state_builder import StateBuilder


class TrajectoryBuilder:

    def __init__(self,

                 backend: BaseBackend,
                 trajectory_backend: BaseTrajectoryBackend,
                 queue: BaseDistributedQueue,
                 config: TrajectoryCollectorConfigHelper,
                 global_config: GlobalConfigHelper,
                 system_producer: SystemEventProducer,
                 trajectory_saver: Saver,
                 state_builder: StateBuilder,
                 workers_load_updated_event: Event,
                 logger=None
                 ):
        self.global_config: GlobalConfigHelper = global_config
        self.config: TrajectoryCollectorConfigHelper = config
        self.run_config: RunConfigHelper = None
        self.logger = logger if logger is not None else get_logger(self.config.logger())
        self.system_producer: SystemEventProducer = system_producer
        self.trajectory_saver: Saver = trajectory_saver
        self.state_builder: StateBuilder = state_builder
        self.state_features: Features = None
        self.execution_cost_calculator: ExecutionCostCalculator = ExecutionCostCalculator(self.global_config)
        self.reward_function: BaseRewardFunction = None
        self.backend = backend
        self.trajectory_backend = trajectory_backend
        self.queue: BaseDistributedQueue = queue
        self.operation_lock = Lock()
        self.is_ready = False
        self.current_run_code = None
        self.current_phase = RunPhase.WAIT
        self.stats_backend: StatsBackend = StatsBackend(global_config=self.global_config, logger=self.logger)
        self.task_to_execute = None
        self.task_completed = 0
        self.task_failed = 0
        self.notified_trajectories = {}
        self.background_pool = ThreadPool(processes=1)
        self.workers_load_updated_event: Event = workers_load_updated_event
        self.subscribe_threads = []

    def add_next_state_to_previous_trajectory(self, current_state, next_trajectory_id):
        previous_trajectory_id = self.trajectory_backend.get_previous_trajectory(only_id=True)
        self.logger.debug('Updating next_state of previous_trajectory with id {}'.format(previous_trajectory_id),
                          resource='TrajectoryBuilder')
        if previous_trajectory_id is not None:
            self.trajectory_backend.update_property(previous_trajectory_id,
                                                    value=current_state,
                                                    prop=TrajectoryProperties.NEXT_STATE,
                                                    compone_key=False)
            previous_trajectory: Trajectory = self.trajectory_backend.get(previous_trajectory_id, compone_key=False)
            if previous_trajectory is None:
                self.logger.error('Previous trajectory with id {} is None'.format(previous_trajectory_id),
                                  resource='TrajectoryBuilder')
            else:
                if previous_trajectory.is_complete(is_context_enabled=self.run_config.is_context_enabled()):
                    self.notify_agent_of_trajectory_completed(previous_trajectory)
        res = self.trajectory_backend.set_previous_trajectory(next_trajectory_id)
        if res is True:
            self.logger.debug('Previous trajectory has been set has {}'
                              .format(next_trajectory_id), resource='TrajectoryBuilder')
        else:
            self.logger.warning('Error while adding {} as previous trajectory'.format(next_trajectory_id),
                                resource='TrajectoryBuilder')
        previous_trajectory_id = previous_trajectory_id if previous_trajectory_id is not None else None
        self.logger.info('Updated next state of previous trajectory {} and new '
                         'trajectory set as new previous trajectory {}'
                         .format(previous_trajectory_id, next_trajectory_id), resource='TrajectoryBuilder')

    def _get_state(self, task_id, task_class):
        if not self.workers_load_updated_event.wait(timeout=10):
            self.logger.warning('waited too long before worker_load_update_event')
        state = self.state_builder.get_state(task_id, task_class)
        self.workers_load_updated_event.clear()
        return state

    def create_trajectory(self, task_id, task_class, timestamp):
        current_state = self._get_state(task_id, task_class)
        trajectory = Trajectory(id=task_id, state=current_state, created_ad=timestamp)
        self.trajectory_backend.save(trajectory.id(), trajectory, use_setnx=True)
        self.logger.info('Trajectory created and saved {}'.format(trajectory), resource='TrajectoryBuilder')
        self.reward_function.post_state_created(task_id)
        self.add_next_state_to_previous_trajectory(current_state, trajectory.id())

    def compute_reward(self, task_id, task_class, runtime, worker_class, failed):
        if self.reward_function is None:
            self.logger.error('No reward function has been set')
            return 0
        if failed is True:
            self.task_failed += 1
            self.logger.info('Task of class {} with id {} failed when executed on worker class {}'
                             .format(task_class, task_id, worker_class), resource='TrajectoryBuilder')
        else:
            waiting_time_struct = self.trajectory_backend.get_task_waiting_time(task_id)
            waiting_time = float(waiting_time_struct['waited'])

            return self.reward_function.compute(
                task_id=task_id,
                task_class=task_class,
                worker_class=worker_class,
                execution_time=runtime,
                waiting_time=waiting_time,
                failed=failed,
                push_trajectory_extra_info=self._push_trajectory_extra_info
            )

    def _push_trajectory_extra_info(self,
                                    trajectory_id,
                                    worker_class,
                                    waiting_time,
                                    waiting_cost,
                                    execution_time,
                                    execution_cost):
        self.update_stats(waiting_time, waiting_cost, execution_time, execution_cost)
        if not self.trajectory_saver.disabled:
            self.trajectory_saver.push_trajectory_extra(
                trajectory_id=trajectory_id,
                field='worker_class',
                value=worker_class
            )
            self.trajectory_saver.push_trajectory_extra(
                trajectory_id=trajectory_id,
                field='execution_info',
                value={
                    'execution_cost': execution_cost,
                    'execution_time': execution_time,
                    'waiting_cost': waiting_cost,
                    'waiting_time': waiting_time,
                }
            )

    def _update_stats(self, waiting_time, waiting_cost, execution_time, execution_cost):
        if self.current_run_code is not None:
            self.stats_backend.save_stats_group_property(
                stats_run_code=self.current_run_code,
                prop='waiting_time',
                value=waiting_time,
                as_list=True
            )
            self.stats_backend.save_stats_group_property(
                stats_run_code=self.current_run_code,
                prop='waiting_cost',
                value=waiting_cost,
                as_list=True
            )
            self.stats_backend.save_stats_group_property(
                stats_run_code=self.current_run_code,
                prop='execution_time',
                value=execution_time,
                as_list=True
            )
            self.stats_backend.save_stats_group_property(
                stats_run_code=self.current_run_code,
                prop='execution_cost',
                value=execution_cost,
                as_list=True
            )
            self.logger.debug('Stats waiting_time, waiting_cost, execution_time and execution_cost have been updated',
                              resource='TrajectoryBuilder')
        else:
            self.logger.warning('No current run code, it is not possible to save stats', resource='TrajectoryBuilder')

    def update_stats(self, waiting_time, waiting_cost, execution_time, execution_cost):
        self.background_pool.apply_async(self._update_stats,
                                         args=(waiting_time, waiting_cost, execution_time, execution_cost))

    def update_trajectory_reward(self, task_id, reward):
        self.trajectory_backend.update_property(trajectory_id=task_id, value=reward, prop=TrajectoryProperties.REWARD)
        self.logger.info('Trajectory reward has been saved on the trajectory', resource='TrajectoryBuilder')
        trajectory = self.trajectory_backend.get(task_id)
        if trajectory is None:
            self.logger.error('Trajectory with id {} is None (error during reward update)'.format(task_id),
                              resource='TrajectoryBuilder')
        else:
            if trajectory.is_complete(is_context_enabled=self.run_config.is_context_enabled()):
                self.notify_agent_of_trajectory_completed(trajectory)

    def notify_agent_of_trajectory_completed(self, trajectory: Trajectory):
        with self.operation_lock:
            if trajectory.id() not in self.notified_trajectories:
                self.logger.info('Trajectory is complete, notifying agent', resource='TrajectoryBuilder')
                self.notified_trajectories[trajectory.id()] = True
                self.system_producer.publish_trajectory_completed_event(trajectory_id=trajectory.id())
            else:
                self.logger.warning(f'Trajectory Completed notification for id {trajectory.id()} called more than once')

    def compute_task_reward(self, task_id, task_class, runtime, worker_class, failed):
        reward = self.compute_reward(task_id, task_class, runtime, worker_class, failed)
        self.task_completed += 1
        self.logger.info('Reward = {} for task name {} and id {}'.format(reward, task_class, task_id),
                         resource='TrajectoryBuilder')
        self.update_trajectory_reward(task_id, reward)
        self.are_all_task_executed()

    def are_all_task_executed(self):
        if self.current_phase == RunPhase.RUN and self.task_to_execute is not None:
            self.logger.debug('task_completed = {} | task_to_execute = {}'
                              .format(self.task_completed, self.task_to_execute), resource='TrajectoryBuilder')
            if self.task_completed == self.task_to_execute:
                # execution completed
                self.logger.info('{} tasks have been executed. The simulation is completed'.format(self.task_completed),
                                 resource='TrajectoryBuilder')
                self.system_producer.publish_execution_completed_event(
                    phase=RunPhase.RUN,
                    task_executed=self.task_completed)

    def handle_start_state_creation_event(self, message_string):
        try:
            if message_string is None:
                self.logger.warning('Received notification of SET on the state generation queue but it is empty',
                                    resource='TrajectoryBuilder')
            else:
                message = json.loads(message_string)
                if 'task_uuid' in message and 'task_class' in message and 'timestamp' in message:
                    self.logger.info('Received task "{}" with uuid "{}" starting environment state generation'
                                     .format(message['task_class'], message['task_uuid']), resource='TrajectoryBuilder')
                    self.create_trajectory(task_id=message['task_uuid'], task_class=message['task_class'],
                                           timestamp=message['timestamp'])
                else:
                    self.logger.warning('Received {} message, but at least one of task_uuid, task_class or'
                                        ' timestamp is missing'
                                        .format(self.config.consumer_queue_state_creation_key()),
                                        resource='TrajectoryBuilder')
        except Exception as e:
            self.logger.exception(e)

    def handle_compute_reward_event(self, message_string):
        try:
            message = json.loads(message_string)
            if message is None:
                self.logger.debug('Received notification of SET on the compute reward queue but it is empty',
                                  resource='TrajectoryBuilder')
            else:
                if 'task_uuid' in message and 'runtime' in message and 'worker_class' in message and 'task_class' in message:
                    self.logger.info('Received compute reward event for task "{}" starting reward computation'
                                     .format(message['task_uuid']), resource='TrajectoryBuilder')
                    self.compute_task_reward(task_id=message['task_uuid'],
                                             task_class=message['task_class'],
                                             runtime=message['runtime'],
                                             worker_class=message['worker_class'],
                                             failed=message['failed'])
                else:
                    self.logger.warning('Received {} message, but at least one of task_uuid, task_class, '
                                        'runtime or worker_class is missing'
                                        .format(self.config.consumer_queue_compute_reward_key()),
                                        resource='TrajectoryBuilder')
        except Exception as e:
            self.logger.exception(e)

    def init(self):
        try:
            if self.is_ready is False:
                state_creation_key = self.config.consumer_queue_state_creation_key()
                compute_reward_key = self.config.consumer_queue_compute_reward_key()
                self.logger.info('Subscribing for {} and {} events'.format(state_creation_key, compute_reward_key),
                                 resource='TrajectoryBuilder')
                self.subscribe_threads.append(
                    self.queue.subscribe(state_creation_key, callback=self.handle_start_state_creation_event))
                self.subscribe_threads.append(
                    self.queue.subscribe(compute_reward_key, callback=self.handle_compute_reward_event))
                self.is_ready = True
        except Exception as e:
            self.logger.exception(e)
            self.system_producer.publish_resource_status_changed_event(
                resource_name='trajectory_collector',
                status=ResourceStatus.ERROR
            )

    def stop(self):
        try:
            self.background_pool.close()
            self.background_pool.join()
            self.queue.close()
            for thread in self.subscribe_threads:
                thread.stop()
        except Exception as e:
            self.logger.exception(e)
        finally:
            self.is_ready = False
