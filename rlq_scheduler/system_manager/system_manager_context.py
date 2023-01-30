import os
import time

from rlq_scheduler.common.config_helper import SystemManagerConfigHelper, MultiRunConfigHelper
from rlq_scheduler.common.resource_context import Context
from rlq_scheduler.common.run_config import generate_run_name
from rlq_scheduler.common.system_status import ResourceStatus
from rlq_scheduler.common.utils.decorators import class_fetch_exceptions
from rlq_scheduler.common.utils.filesystem import get_absolute_path
from rlq_scheduler.system_manager.celery_monitor import CeleryMonitor
from rlq_scheduler.system_manager.run_manager.run_manager import RunManager
from rlq_scheduler.system_manager.system_manager import SystemManager


class SystemManagerContext(Context):

    def __init__(self,
                 config_filename,
                 global_config_filename,
                 multi_run_config_filename,
                 celery_app,
                 system_consumer_callbacks,
                 ):
        self.config: SystemManagerConfigHelper = SystemManagerConfigHelper(config_path=config_filename)
        self.multi_run_config: MultiRunConfigHelper = MultiRunConfigHelper(config_path=multi_run_config_filename)
        super(SystemManagerContext, self).__init__(global_config_filename=global_config_filename,
                                                   system_consumer_callbacks=system_consumer_callbacks,
                                                   config=self.config,
                                                   name='SystemManager')
        self.celery_app = celery_app
        self.celery_monitor: CeleryMonitor = None
        self.system_manager: SystemManager = None
        self.run_manager: RunManager = None

    @class_fetch_exceptions(publish_error=True, is_context=True)
    def init(self):
        super(SystemManagerContext, self).init()
        self.init_resource()

    @class_fetch_exceptions(publish_error=True, is_context=True)
    def init_resource(self):
        self.logger.info('Called init resource', resource='SystemManagerContext')
        if self.resources_initialized is False:
            self._init_primary_components()
            self.celery_monitor: CeleryMonitor = CeleryMonitor(
                celery_app=self.celery_app,
                global_config=self.global_config,
                logger=self.logger
            )
            self.system_manager: SystemManager = SystemManager(
                config=self.config,
                global_config=self.global_config,
                system_producer=self.system_producer,
                celery_monitor=self.celery_monitor,
                logger=self.logger
            )
            self.run_manager: RunManager = RunManager(
                config=self.multi_run_config,
                system_manager_config=self.config,
                global_config=self.global_config,
                system_manager=self.system_manager,
                system_producer=self.system_producer,
                config_folder=self.config.config_folder(),
                logger=self.logger
            )
            super().start_run(start_time=None)
            time.sleep(0.1)
            self.system_manager.start()
            self.run_manager.start()
            self.change_resource_status(ResourceStatus.RUNNING)
            self.resources_initialized = True
        else:
            self.logger.warning('Init resources called more than once for {}'.format(self.name),
                                resource='SystemManagerContext')

    def start_run(self, start_time: float or None):
        self.current_run_start_execution_time = start_time

    def save_stats_on_disk(self):
        stats = self.system_manager.stats_backend.load(run_code=self.current_run_code)
        self.logger.debug('generate run name kwargs: run_code={} | task_executed={} | start_time={} | extension={}'
                          .format(self.current_run_code, self.run_manager.current_tasks_executed,
                                  self.current_run_prepare_time, 'json'), resource='SystemManagerContext')
        filename = generate_run_name(
            run_code=self.current_run_code,
            task_executed=self.current_run_config.tasks_to_generate_total_number(),
            start_time=self.current_run_prepare_time,
            extension='json')
        agent_name = stats.get_agent_name()
        agent_mode = stats.get_agent_mode()
        if self.global_config.object_handler_type() == 'minio':
            folder_path = os.path.join(self.current_run_config.run_name_prefix(),
                                       self.config.stats_folder_path(),
                                       agent_mode, agent_name)
        else:
            folder_path = get_absolute_path(os.path.join(
                self.current_run_config.run_name_prefix(),
                self.config.stats_folder_path(),
                agent_mode, agent_name))
        self.object_handler.save(
            obj=stats.to_dict(),
            filename=filename,
            path=folder_path,
            max_retries=5,
            trial=0,
            wait_timeout=60
        )
        self._save_run_on_db(stats.db_stats())
        # save_file(folder_path, filename, content=stats.to_dict(), is_json=True)
        # publish run completed event
        self.system_producer.publish_run_completed_event(run_code=self.current_run_code)

    def _save_run_on_db(self, db_stats):
        self.trajectory_saver.db.save(self.current_run_config.run_name_prefix(), document=db_stats)

    def stop(self):
        self.system_manager.stop()
        self.run_manager.stop()
        super().stop()

    def resources(self):
        resources = super().resources()
        resources.update({
            'config': self.config,
            'multi_run_config': self.multi_run_config,
            'celery_monitor': self.celery_monitor,
            'system_manager': self.system_manager,
            'run_manager': self.run_manager
        })
        return resources
