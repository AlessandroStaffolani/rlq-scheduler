import time

from rlq_scheduler.common.backends.backend_factory import get_backend_adapter
from rlq_scheduler.common.config_helper import GlobalConfigHelper, BaseConfigHelper, RunConfigHelper
from rlq_scheduler.common.object_handler import create_object_handler, MinioObjectHandler, ObjectHandler
from rlq_scheduler.common.run_config import RunConfig
from rlq_scheduler.common.stats import RunStats, StatsBackend
from rlq_scheduler.common.system_events.consumer import SystemEventConsumer
from rlq_scheduler.common.system_events.event import RunPhase
from rlq_scheduler.common.system_events.producer import SystemEventProducer
from rlq_scheduler.common.system_status import ResourceStatus
from rlq_scheduler.common.trajectory_saver.saver import Saver
from rlq_scheduler.common.utils.decorators import class_fetch_exceptions
from rlq_scheduler.common.utils.logger import get_logger
from rlq_scheduler.common.utils.string_utils import camel_to_snake, snake_to_camel


class Context:

    def __init__(self,
                 global_config_filename: str,
                 name,
                 config=None,
                 system_consumer_callbacks=None
                 ):
        self.global_config = GlobalConfigHelper(config_path=global_config_filename)
        self.config: BaseConfigHelper = config
        if self.config is None:
            self.logger = get_logger(self.global_config.logger())
        else:
            self.logger = get_logger(self.config.logger())
        self.name = camel_to_snake(name)
        self.visual_name = snake_to_camel(self.name)
        self.system_producer: SystemEventProducer = None
        self.system_consumer: SystemEventConsumer = None
        self.object_handler: ObjectHandler or MinioObjectHandler = create_object_handler(
            config=self.global_config, logger=self.logger)
        self.trajectory_saver: Saver = None
        self.system_consumer_callbacks = system_consumer_callbacks
        self.current_phase = RunPhase.WAIT
        self.current_run_code = None
        self.current_run_config: RunConfigHelper = None
        self.current_run_prepare_time = None
        self.current_run_start_execution_time = None
        self.current_run_end_execution_time = None
        self.current_run_end_time = None
        self.previous_run_code = None
        self.current_run_stats: RunStats = RunStats()
        self.stats_backend: StatsBackend = None
        self.status: ResourceStatus = ResourceStatus.NOT_READY
        self.resources_initialized = False

    @class_fetch_exceptions(publish_error=True, is_context=True)
    def init(self):
        self.logger.info('Starting initialization process for {} resources'.format(self.name),
                         resource='ResourceContext')
        self.system_producer: SystemEventProducer = SystemEventProducer(
            global_config=self.global_config,
            logger=self.logger
        )
        self.system_consumer: SystemEventConsumer = SystemEventConsumer(
            global_config=self.global_config,
            logger=self.logger,
            callbacks_context=self,
            **self.system_consumer_callbacks
        )
        self.system_consumer.consume()
        time.sleep(0.01)
        self.system_producer.publish_resource_status_changed_event(
            resource_name=self.name,
            status=self.status
        )

    def init_resource(self):
        if self.resources_initialized is False:
            self._init_primary_components()
            self._init_final_action()
            self.resources_initialized = True
        else:
            self.logger.warning('Init resources called more than once for {}'.format(self.name),
                                resource='ResourceContext')

    def _init_primary_components(self):
        self.stats_backend: StatsBackend = StatsBackend(global_config=self.global_config, logger=self.logger)
        self._init_trajectory_saver()

    def _init_trajectory_saver(self):
        self.trajectory_saver: Saver = Saver(global_config=self.global_config, logger=self.logger)
        self.trajectory_saver.init()

    def _init_final_action(self):
        self.change_resource_status(status=ResourceStatus.WAITING)
        self.logger.info('Initialized {} resources'.format(self.visual_name), resource='ResourceContext')

    def prepare_run(self, run_config: RunConfig, prepare_time: float or None):
        self.logger.run_code = run_config.run_code
        self.current_run_code = run_config.run_code
        self.current_run_config = run_config.config
        self.current_run_prepare_time = prepare_time
        self.current_run_stats = RunStats(run_code=run_config.run_code)
        if run_config.config.is_trajectory_saving_enabled():
            if self.trajectory_saver.disabled:
                self.trajectory_saver.disabled = False
            self.trajectory_saver.current_run_code = run_config.run_code
        else:
            self.trajectory_saver.disabled = True

    def stop_run_resources(self, end_run_time: float or None):
        self.current_run_end_time = end_run_time

    def resources(self):
        return {
            'global_config': self.global_config,
            'system_producer': self.system_producer,
            'system_consumer': self.system_consumer,
            'current_run_code': self.current_run_code,
            'current_run_stats': self.current_run_stats,
            'stats_backend': self.stats_backend,
            'logger': self.logger
        }

    @class_fetch_exceptions(publish_error=True, is_context=True)
    def start_run(self, start_time: float or None):
        self.current_run_start_execution_time = start_time
        self.logger.info('{} is starting a new run, with code: {}'.format(self.visual_name, self.current_run_code),
                         resource='ResourceContext')
        self.logger.info('Global config are: {}'.format(self.global_config), resource='ResourceContext')
        self.logger.info('{} config are: {}'.format(self.visual_name, self.config), resource='ResourceContext')

    @class_fetch_exceptions(publish_error=True, is_context=True)
    def stop(self):
        self.system_consumer.stop()
        self.stats_backend.backend.close()
        self.trajectory_saver.stop()
        self.change_resource_status(ResourceStatus.STOPPED)
        self.logger.info('{} have been stopped'.format(self.name), resource='ResourceContext')

    def change_resource_status(self, status: ResourceStatus):
        if status != self.status:
            self.status = status
            if self.system_producer is not None:
                self.system_producer.publish_resource_status_changed_event(
                    resource_name=self.name,
                    status=status
                )

    def save_stats_property_value(self, prop, value):
        result = self.stats_backend.save_stats_group_property(
            stats_run_code=self.current_run_code,
            prop=prop,
            value=value
        )
        if result is True:
            self.logger.debug('Added {} to stats, with value: {}'.format(prop, value),
                              resource='ResourceContext')
        else:
            self.logger.warning('Impossible to save {} to stats, using value: {}'.format(prop, value),
                                resource='ResourceContext')

    def _init_backend(self, backed_type):
        backend_class = get_backend_adapter(self.global_config.backend_adapter(), backed_type=backed_type)
        return backend_class(config=self.global_config.backend_config(), logger=self.logger)
