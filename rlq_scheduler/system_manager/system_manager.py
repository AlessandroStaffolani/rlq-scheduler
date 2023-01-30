import logging
from multiprocessing.pool import ThreadPool

import redis

from rlq_scheduler.common.config_helper import GlobalConfigHelper, SystemManagerConfigHelper
from rlq_scheduler.common.stats import StatsBackend
from rlq_scheduler.common.system_events.event import *
from rlq_scheduler.common.system_events.producer import SystemEventProducer
from rlq_scheduler.common.system_status import system_status_from_resources_status
from rlq_scheduler.common.utils.decorators import class_fetch_exceptions
from rlq_scheduler.common.utils.logger import get_logger
from rlq_scheduler.system_manager.celery_monitor import CeleryMonitor


class SystemManager:

    def __init__(self,
                 config: SystemManagerConfigHelper,
                 global_config: GlobalConfigHelper,
                 system_producer: SystemEventProducer,
                 celery_monitor: CeleryMonitor,
                 logger: logging.Logger = None):
        self.global_config: GlobalConfigHelper = global_config
        self.config: SystemManagerConfigHelper = config
        self.celery_monitor: CeleryMonitor = celery_monitor
        self.logger = logger if logger is not None else get_logger(self.config.logger())
        self.stats_backend: StatsBackend = StatsBackend(global_config=self.global_config, logger=self.logger)
        self.producer: SystemEventProducer = system_producer
        self.execution_pool = ThreadPool(processes=1)
        self.is_running = False
        self.system_status: SystemStatus = SystemStatus.NOT_READY
        self.celery_status = {
            'status': ResourceStatus.NOT_READY,
            'message': None
        }
        self.resources_status = {resource: {'status': ResourceStatus.NOT_READY, 'message': None}
                                 for resource in self.config.system_resources()}
        self.current_run_code = None
        self.stats_groups = {
            'global_stats': False,
            'agent_stats': False,
            'execution_history_stats': False,
            'tasks_generated': False
        }

    @class_fetch_exceptions(publish_error=True, is_context=True, producer_property='producer')
    def resource_has_changed_status(self, resource_name, resource_status: ResourceStatus, extras=None):
        self.logger.debug('Resource name: {} | resource_status: {} | current resources status: {}'
                          .format(resource_name, resource_status, self.resources_status),
                          resource='SystemManager')
        if resource_name in self.resources_status and self.resources_status[resource_name]['status'] != resource_status:
            self.resources_status[resource_name]['status'] = resource_status
            if resource_status == ResourceStatus.ERROR and extras is not None and 'message' in extras:
                self.resources_status[resource_name]['message'] = extras['message']
            self.check_system_status()
        elif resource_name == 'celery':
            self.celery_status['status'] = resource_status
            if extras is not None and 'message' in extras:
                self.celery_status['message'] = extras['message']
            self.check_system_status()

    def check_system_status(self):
        if self.celery_status['status'] == ResourceStatus.RUNNING:
            # celery is RUNNING, check other resources
            resource_status_array = {
                ResourceStatus.NOT_READY: [],
                ResourceStatus.WAITING: [],
                ResourceStatus.READY: [],
                ResourceStatus.RUNNING: [],
                ResourceStatus.STOPPED: [],
                ResourceStatus.ERROR: []
            }
            messages = []
            for resource, value in self.resources_status.items():
                resource_status_array[value['status']].append(resource)
                if value['message'] is not None:
                    messages.append(value['message'])

            self.logger.debug('Computing current system status using resource_status_array = {}'
                              .format(resource_status_array), resource='SystemManager')

            status = system_status_from_resources_status(
                resource_status_array,
                n_resources=len(self.config.system_resources()),
                current_status=self.system_status
            )
            self.set_system_status(status)
        else:
            self.set_system_status(status=SystemStatus(self.celery_status['status'].value))

    def check_celery_status(self, timeout=300, max_retries=1, background=False):
        if background:
            self.execution_pool.apply_async(self._check_celery_status,
                                            kwds={'timeout': timeout, 'max_retries': max_retries})
        else:
            self._check_celery_status(timeout, max_retries=max_retries)

    def set_system_status(self, status: SystemStatus):
        if status != self.system_status:
            self.system_status = status
            self.producer.publish_system_status_changed_event(status)
        else:
            self.logger.debug('Set SystemStatus skipped, because status did not change',
                              resource='SystemManager')

    def _check_celery_status(self, timeout=300, retries=1, max_retries=1):
        if retries <= max_retries:
            self.logger.info('Checking celery status at trial {}'.format(retries), resource='SystemManager')
            time_waited = 0
            celery_is_running = False
            trial = 1
            while time_waited < timeout and celery_is_running is False:
                self.logger.debug('Celery status check trial number {}'.format(trial), resource='SystemManager')
                response = self.celery_monitor.status()
                if response['status'] == ResourceStatus.RUNNING:
                    celery_is_running = True
                    if self.celery_status['status'] != ResourceStatus.RUNNING:
                        self.celery_status['status'] = ResourceStatus.RUNNING
                        self.producer.publish_resource_status_changed_event('celery', status=ResourceStatus.RUNNING)
                else:
                    next_check = 2 ** trial
                    trial += 1
                    self.logger.debug('Celery is not ready yet, next trial in {} seconds'.format(next_check),
                                      resource='SystemManager')
                    time.sleep(next_check)
                    time_waited += next_check
            if celery_is_running is False:
                self.logger.warning('Celery is not running after {} seconds of waiting at retry {}'
                                    .format(time_waited, retries), resource='SystemManager')
                self._check_celery_status(timeout, retries + 1, max_retries)
        else:
            self.celery_status['status'] = ResourceStatus.ERROR
            self.producer.publish_resource_status_changed_event(
                'celery',
                status=ResourceStatus.ERROR,
                message='Celery is unreachable after {} seconds'.format(timeout))
            self.logger.error('Celery is not running after {} seconds of waiting and {} retries'
                              .format(timeout, retries), resource='SystemManager')

    def start(self):
        try:
            self.logger.info('SystemManager is starting', resource='SystemManager')
            self.producer.publish_system_status_changed_event(self.system_status)
            self.is_running = True
            self.check_celery_status(background=True, max_retries=3)
        except redis.ConnectionError as e:
            self.logger.error('Error while connecting to redis. Error message: {}'.format(e),
                              resource='SystemManager')
        except Exception as e:
            self.logger.exception(e)

    def stop(self):
        try:
            self.is_running = False
            self.logger.info('SystemManager has been stopped', resource='SystemManager')
        except Exception as e:
            self.logger.exception(e)
