import logging

import redis

from rlq_scheduler.common.config_helper import GlobalConfigHelper
from rlq_scheduler.common.redis_connection import RedisConnectionFactory
from rlq_scheduler.common.system_events.event import *


class SystemEventProducer:

    def __init__(self,
                 global_config: GlobalConfigHelper,
                 logger: logging.Logger,
                 host=None):
        self.global_config: GlobalConfigHelper = global_config
        self.logger: logging.Logger = logger
        redis_config = self.global_config.redis_config()
        if host is not None:
            redis_config['host'] = host
        self.redis_connection_factory = RedisConnectionFactory(redis_config)
        self.redis_connection: redis.Redis = self.redis_connection_factory.get_connection()
        self.system_info_topic = self.global_config.redis_system_info_topic()

    def publish(self, event: Event):
        self.redis_connection.publish(self.system_info_topic, event.to_json())
        self.logger.info('Published event {} with payload: {}'.format(event, event.payload), resource='SystemProducer')

    def publish_generic_event(self, payload=None, **kwargs):
        event = Event(payload=payload, **kwargs)
        self.publish(event)

    def publish_system_status_changed_event(self, status: SystemStatus, **kwargs):
        event = SystemStatusChangedEvent(system_status=status, **kwargs)
        self.publish(event)

    def publish_resource_status_changed_event(self, resource_name: str, status: ResourceStatus, **kwargs):
        event = ResourceStatusChangedEvent(resource_name=resource_name, resource_status=status, **kwargs)
        self.publish(event)

    def publish_prepare_new_run_event(self, run_config: RunConfig, **kwargs):
        event = PrepareNewRunEvent(new_run_config=run_config, **kwargs)
        self.publish(event)

    def publish_start_run_event(self, run_code, **kwargs):
        event = StartRunEvent(run_code=run_code, **kwargs)
        self.publish(event)

    def publish_stats_updated_event(self, run_code, stat_group, stat_property=None, **kwargs):
        event = StatsUpdateEvent(run_code=run_code, stat_group=stat_group, stat_property=stat_property, **kwargs)
        self.publish(event)

    def publish_scheduling_started_event(self, phase: RunPhase, task_to_generate: int,
                                         task_to_schedule_config: dict, **kwargs):
        event = SchedulingStartedEvent(phase, task_to_generate, task_to_schedule_config, **kwargs)
        self.publish(event)

    def publish_trajectory_completed_event(self, trajectory_id: str, **kwargs):
        event = TrajectoryCompletedEvent(trajectory_id, **kwargs)
        self.publish(event)

    def publish_scheduling_completed_event(self, phase: RunPhase, task_scheduled: int, **kwargs):
        event = SchedulingCompletedEvent(phase, task_scheduled, **kwargs)
        self.publish(event)

    def publish_execution_completed_event(self, phase: RunPhase, task_executed: int, **kwargs):
        event = ExecutionCompletedEvent(phase, task_executed, **kwargs)
        self.publish(event)

    def publish_run_completed_event(self, run_code: str, **kwargs):
        event = RunCompletedEvent(run_code=run_code, **kwargs)
        self.publish(event)
