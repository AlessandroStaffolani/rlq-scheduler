import numpy as np

from rlq_scheduler.common.config_helper import TaskGeneratorConfigHelper
from rlq_scheduler.common.resource_context import Context
from rlq_scheduler.common.run_config import RunConfig
from rlq_scheduler.common.system_status import ResourceStatus
from rlq_scheduler.common.utils.decorators import class_fetch_exceptions
from rlq_scheduler.task_generator.task_generator import TaskGenerator


class TaskGeneratorContext(Context):

    def __init__(self,
                 config_filename,
                 global_config_filename,
                 system_consumer_callbacks
                 ):
        self.config: TaskGeneratorConfigHelper = TaskGeneratorConfigHelper(config_path=config_filename)
        super(TaskGeneratorContext, self).__init__(global_config_filename=global_config_filename,
                                                   system_consumer_callbacks=system_consumer_callbacks,
                                                   config=self.config,
                                                   name='TaskGenerator')
        self.task_generator: TaskGenerator = None

    @class_fetch_exceptions(publish_error=True, is_context=True)
    def init_resource(self):
        if self.resources_initialized is False:
            self._init_primary_components()
            self.task_generator = TaskGenerator(
                config=self.config,
                global_config=self.global_config,
                system_producer=self.system_producer,
                logger=self.logger,
                trajectory_saver=self.trajectory_saver,
                test_mode=False
            )
            self.task_generator.start()
            self._init_final_action()
            self.resources_initialized = True
        else:
            self.logger.warning('Init resources called more than once for {}'.format(self.name),
                                resource='TaskGeneratorContext')

    @class_fetch_exceptions(publish_error=True, is_context=True)
    def prepare_run(self, run_config: RunConfig, prepare_time: float or None):
        try:
            super().prepare_run(run_config, prepare_time)
            self.task_generator.run_config = run_config.config
            self.task_generator.tasks_scheduled = 0
            self.task_generator.tasks_bootstrapped = 0
            self.task_generator.scheduled_task_history = []
            self.task_generator.test_waiting_time_history = []
            self.task_generator.scheduled_task_stats = {}
            self.task_generator.random = np.random.RandomState(run_config.config.task_generator_random_seed())
            self.task_generator.init_datasets()
            self.logger.info('Task Generator configured with random seed: {}'
                              .format(run_config.config.task_generator_random_seed()))
            self.change_resource_status(ResourceStatus.READY)
        except Exception as e:
            self.logger.exception(e)
            self.change_resource_status(ResourceStatus.ERROR)

    def start_run(self, start_time: float or None):
        super().start_run(start_time=start_time)
        global_stats = self.task_generator.get_global_stats(
            prepare_time=self.current_run_prepare_time,
            start_execution_time=self.current_run_start_execution_time
        )
        self.current_run_stats.set_global_stats(**global_stats)
        result = self.stats_backend.save_stats_group(
            stats_run_code=self.current_run_code,
            group=self.current_run_stats.global_stats)
        if result is True:
            self.logger.info('Global stats have been saved', resource='TaskGeneratorContext')
            self.system_producer.publish_stats_updated_event(run_code=self.current_run_code,
                                                             stat_group='global_stats')
        else:
            self.logger.warning('Error while saving global stats', resource='TaskGeneratorContext')
        if not self.trajectory_saver.disabled:
            self.trajectory_saver.save_run_info(
                run_code=self.current_run_code,
                tasks_to_generate=self.current_run_config.task_generator_config(),
                features_enabled=self.current_run_config.features_enabled(),
                tasks_config=self.current_run_config.task_classes(),
                workers_config=self.current_run_config.worker_classes(),
                run_functions=self.current_run_config.functions(),
                state_features=self.current_run_config.state(),
                context_features=self.current_run_config.context_features(),
                agent_config=self.current_run_config.agent_config(self.current_run_config.agent_type())
            )
        self.change_resource_status(ResourceStatus.RUNNING)
        if self.current_run_config.is_google_traces_mode_enabled() and self.current_run_config.is_evaluation_enabled():
            self.task_generator.schedule_eval_tasks()
        else:
            if self.current_run_config.is_bootstrapping_enabled() \
                    and self.current_run_config.tasks_bootstrapping_tasks_to_generate() > 0:
                self.task_generator.schedule_bootstrapping_tasks()
            else:
                self.task_generator.schedule_tasks()

    def stop_run_resources(self, end_run_time: float or None):
        super().stop_run_resources(end_run_time)
        self.change_resource_status(ResourceStatus.WAITING)

    def stop(self):
        self.task_generator.stop()
        super().stop()

    def resources(self):
        resources = super().resources()
        resources.update({
            'config': self.config,
            'task_generator': self.task_generator
        })
        return resources
