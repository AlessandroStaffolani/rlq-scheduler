from threading import Event
from multiprocessing.pool import ThreadPool

from rlq_scheduler.common.backends.base_backend import BaseBackend, BaseTrajectoryBackend
from rlq_scheduler.common.config_helper import TrajectoryCollectorConfigHelper
from rlq_scheduler.common.distributed_queue.base_queue import BaseDistributedQueue
from rlq_scheduler.common.distributed_queue.queue_factory import get_distributed_queue
from rlq_scheduler.common.resource_context import Context
from rlq_scheduler.common.reward_function import get_reward_function
from rlq_scheduler.common.run_config import RunConfig
from rlq_scheduler.common.state.state import Features
from rlq_scheduler.common.system_status import ResourceStatus
from rlq_scheduler.common.utils.decorators import class_fetch_exceptions
from rlq_scheduler.trajectory_collector.consumer.consumer import Consumer
from rlq_scheduler.common.state.state_builder import StateBuilder
from rlq_scheduler.trajectory_collector.trajectory_builder import TrajectoryBuilder
from rlq_scheduler.trajectory_collector.workers_state_builder import WorkersStateBuilder


class TrajectoryCollectorContext(Context):

    def __init__(self,
                 config_filename,
                 global_config_filename,
                 celery_app,
                 system_consumer_callbacks
                 ):
        self.config: TrajectoryCollectorConfigHelper = TrajectoryCollectorConfigHelper(config_path=config_filename)
        super(TrajectoryCollectorContext, self).__init__(global_config_filename=global_config_filename,
                                                         system_consumer_callbacks=system_consumer_callbacks,
                                                         config=self.config,
                                                         name='TrajectoryCollector')
        self.celery_app = celery_app
        self.distributed_queue: BaseDistributedQueue = None
        self.backend: BaseBackend = None
        self.trajectory_backend: BaseTrajectoryBackend = None
        self.workers_state_builder: WorkersStateBuilder = None
        self.state_builder: StateBuilder = None
        self.consumer: Consumer = None
        self.trajectory_builder: TrajectoryBuilder = None
        self.workers_load_updated_event: Event = Event()
        self.async_worker = ThreadPool(processes=2)

    @class_fetch_exceptions(publish_error=True, is_context=True)
    def init_resource(self):
        if self.resources_initialized is False:
            self._init_primary_components()
            distributed_queue_class = get_distributed_queue(self.config.consumer_queue_type())
            self.distributed_queue: BaseDistributedQueue = distributed_queue_class(self.config.consumer_queue_config(),
                                                                                   self.logger)
            self.backend: BaseBackend = self._init_backend(backed_type='base')
            self.trajectory_backend: BaseTrajectoryBackend = self._init_backend(backed_type='trajectory')
            self.state_builder: StateBuilder = StateBuilder(
                global_config=self.global_config,
                logger=self.logger,
                is_workers_load_local=True
            )
            if self.config.is_worker_state_enabled() is True:
                self.workers_state_builder: WorkersStateBuilder = WorkersStateBuilder(
                    celery_app=self.celery_app,
                    backend=self.backend,
                    config=self.config,
                    global_config=self.global_config,
                    system_producer=self.system_producer,
                    state_builder=self.state_builder,
                    logger=self.logger
                )
            self.consumer: Consumer = Consumer(
                celery_app=self.celery_app,
                trajectory_backend=self.trajectory_backend,
                config=self.config,
                global_config=self.global_config,
                state_builder=self.state_builder,
                workers_load_updated_event=self.workers_load_updated_event,
                async_worker=self.async_worker,
                logger=self.logger)
            self.trajectory_builder: TrajectoryBuilder = TrajectoryBuilder(
                backend=self.backend,
                trajectory_backend=self.trajectory_backend,
                queue=self.distributed_queue,
                config=self.config,
                global_config=self.global_config,
                system_producer=self.system_producer,
                trajectory_saver=self.trajectory_saver,
                state_builder=self.state_builder,
                workers_load_updated_event=self.workers_load_updated_event,
                logger=self.logger
            )
            self.consumer.start()
            self.trajectory_builder.init()
            self._init_final_action()
            self.resources_initialized = True
        else:
            self.logger.warning('Init resources called more than once for {}'.format(self.name),
                                resource='TrajectoryCollectorContext')

    def _clean_backend(self):
        trajectories_pattern = f'{self.global_config.backend_trajectory_prefix()}_*'
        previous_trajectory_pattern = f'{self.global_config.backend_previous_trajectory_key()}'
        task_waiting_time_pattern = f'{self.global_config.backend_task_waiting_time_prefix()}_*'
        validation_reward_pattern = f'{self.global_config.backend_validation_reward_prefix()}_*'
        assignments_history_pattern = f'{self.global_config.backend_assignment_entry_prefix()}_*'
        self.trajectory_backend.delete_all(trajectories_pattern)
        self.trajectory_backend.delete_all(previous_trajectory_pattern)
        self.trajectory_backend.delete_all(task_waiting_time_pattern)
        self.trajectory_backend.delete_all(validation_reward_pattern)
        self.trajectory_backend.delete_all(assignments_history_pattern)
        self.trajectory_backend.delete_all(self.global_config.state_builder_resource_usage_key())
        self.trajectory_backend.delete_all(self.global_config.state_builder_task_frequency_key())
        self.trajectory_backend.delete_all(self.global_config.state_builder_pool_load_key())
        self.trajectory_backend.delete_all(self.global_config.state_builder_pool_utilization_key())

    @class_fetch_exceptions(publish_error=True, is_context=True)
    def prepare_run(self, run_config: RunConfig, prepare_time: float or None):
        try:
            super().prepare_run(run_config, prepare_time)
            self._clean_backend()
            features = Features(
                global_config=self.global_config,
                run_config=run_config.config,
                worker_classes=run_config.config.available_worker_classes(),
                task_classes=run_config.config.available_tasks_classes())
            self.trajectory_builder.run_config = run_config.config
            self.trajectory_builder.task_failed = 0
            self.trajectory_builder.current_run_code = run_config.run_code
            self.trajectory_builder.task_completed = run_config.config.tasks_to_skip_total()
            self.trajectory_builder.task_to_execute = run_config.config.tasks_to_generate_total_number()
            self.trajectory_builder.execution_cost_calculator.run_config = run_config.config
            self.trajectory_builder.execution_cost_calculator.init_regression_model()
            self.trajectory_builder.reward_function = get_reward_function(
                global_config=self.global_config,
                run_config=run_config.config,
                execution_cost_calculator=self.trajectory_builder.execution_cost_calculator,
                logger=self.logger
            )
            self.logger.info(f'Initialized reward function {self.trajectory_builder.reward_function}',
                             resource='TrajectoryCollectorContext')
            self.trajectory_builder.notified_trajectories = {}
            self.trajectory_builder.state_features = features
            self.consumer.run_config = run_config.config
            self.consumer.celery_app_state.clear()
            self.state_builder.set_run_config(run_config.config)
            self.state_builder.set_state_features(features)
            self.state_builder.upload_pool_load_on_shared_memory()
            if self.config.is_worker_state_enabled() is True:
                self.workers_state_builder.run_config = run_config.config
                self.workers_state_builder.is_ready = False
                self.workers_state_builder.start()
            else:
                self.change_resource_status(ResourceStatus.READY)
        except Exception as e:
            self.logger.exception(e)
            self.change_resource_status(ResourceStatus.ERROR)

    def stop_run_resources(self, end_run_time: float or None):
        super().stop_run_resources(end_run_time)
        if self.config.is_worker_state_enabled() is True:
            self.workers_state_builder.stop()
        self.change_resource_status(ResourceStatus.WAITING)

    def save_tasks_succeeded_and_failed_stat(self, task_completed, task_failed):
        self.save_stats_property_value('task_succeeded', value=task_completed - task_failed)
        self.save_stats_property_value('task_failed', value=task_failed)

    def start_run(self, start_time: float or None):
        super().start_run(start_time=start_time)
        self.change_resource_status(ResourceStatus.RUNNING)

    def stop(self):
        self.consumer.stop()
        if self.config.is_worker_state_enabled() is True:
            self.workers_state_builder.stop()
        self.trajectory_builder.stop()
        self.state_builder.backend.close()
        self.async_worker.close()
        super().stop()

    def resources(self):
        resources = super().resources()
        resources.update({
            'distributed_queue': self.distributed_queue,
            'backend': self.backend,
            'trajectory_backend': self.trajectory_backend,
            'trajectory_builder': self.trajectory_builder,
            'consumer': self.consumer,
            'workers_state_builder': self.workers_state_builder
        })
        return resources


