import logging
from datetime import datetime

import redis

from rlq_scheduler.common.config_helper import GlobalConfigHelper
from rlq_scheduler.common.redis_connection import RedisConnectionFactory
from rlq_scheduler.common.system_events.event import *
from rlq_scheduler.common.utils.decorators import class_fetch_exceptions


class SystemEventConsumer:

    def __init__(self,
                 global_config: GlobalConfigHelper,
                 logger: logging.Logger,
                 host=None,
                 generic_event_callback=None,
                 system_status_changed_event_callback=None,
                 resource_status_changed_event_callback=None,
                 prepare_new_run_event_callback=None,
                 start_run_event_callback=None,
                 stats_updated_event_callback=None,
                 scheduling_started_event_callback=None,
                 trajectory_completed_event_callback=None,
                 scheduling_completed_event_callback=None,
                 execution_completed_event_callback=None,
                 run_completed_event_callback=None,
                 callbacks_context=None):
        self.name = 'SystemEventConsumer'
        self.global_config: GlobalConfigHelper = global_config
        self.logger: logging.Logger = logger
        redis_config = self.global_config.redis_config()
        if host is not None:
            redis_config['host'] = host
        self.redis_connection_factory = RedisConnectionFactory(redis_config)
        self.redis_connection: redis.Redis = self.redis_connection_factory.get_connection()
        self.system_info_topic = self.global_config.redis_system_info_topic()
        self.pubsub = None
        self.consumer_thread = None
        self.is_started = False
        self.callbacks_context = callbacks_context
        self.event_switcher = {
            SystemEvent.GENERIC: {
                'wrapper_callback': self._generic_event_callback_wrapper,
                'callback': generic_event_callback
            },
            SystemEvent.SYSTEM_STATUS_CHANGED: {
                'wrapper_callback': self._system_status_changed_event_callback_wrapper,
                'callback': system_status_changed_event_callback
            },
            SystemEvent.RESOURCE_STATUS_CHANGED: {
                'wrapper_callback': self._resource_status_changed_event_callback_wrapper,
                'callback': resource_status_changed_event_callback
            },
            SystemEvent.PREPARE_NEW_RUN: {
                'wrapper_callback': self._prepare_new_run_event_callback_wrapper,
                'callback': prepare_new_run_event_callback
            },
            SystemEvent.START_RUN: {
                'wrapper_callback': self._start_run_event_callback_wrapper,
                'callback': start_run_event_callback
            },
            SystemEvent.STATS_UPDATED: {
                'wrapper_callback': self._stats_updated_event_callback_wrapper,
                'callback': stats_updated_event_callback
            },
            SystemEvent.SCHEDULING_STARTED: {
                'wrapper_callback': self._scheduling_started_event_callback_wrapper,
                'callback': scheduling_started_event_callback
            },
            SystemEvent.TRAJECTORY_COMPLETED: {
                'wrapper_callback': self._trajectory_completed_event_callback_wrapper,
                'callback': trajectory_completed_event_callback
            },
            SystemEvent.SCHEDULING_COMPLETED: {
                'wrapper_callback': self._scheduling_completed_event_callback_wrapper,
                'callback': scheduling_completed_event_callback
            },
            SystemEvent.EXECUTION_COMPLETED: {
                'wrapper_callback': self._execution_completed_event_callback_wrapper,
                'callback': execution_completed_event_callback
            },
            SystemEvent.RUN_COMPLETED: {
                'wrapper_callback': self._run_completed_event_callback_wrapper,
                'callback': run_completed_event_callback
            }
        }

    def consume(self):
        self.logger.info('{} is going to subscribe for {} events'.format(self.name, self.system_info_topic),
                         resource='SystemConsumer')
        self.pubsub: redis.client.PubSub = self.redis_connection.pubsub()
        self.pubsub.subscribe(**{self.system_info_topic: self.event_callback})
        self.consumer_thread = self.pubsub.run_in_thread(sleep_time=0.001)
        self.is_started = True

    def stop(self):
        if self.consumer_thread is not None:
            self.consumer_thread.stop()
        if self.pubsub is not None:
            self.pubsub.close()
            self.pubsub.connection_pool.disconnect()
        self.logger.info('{} stopped'.format(self.name), resource='SystemConsumer')

    def event_callback(self, message):
        try:
            if message['type'] == 'message':
                event_json_data = message['data']
                event: Event = Event.from_json(event_json_data)
                if event.type in self.event_switcher:
                    wrapper_callback = self.event_switcher[event.type]['wrapper_callback']
                    wrapper_callback(event)
                else:
                    self.logger.error('No callback for event of type {}'.format(event.type), resource='SystemConsumer')
            if message['type'] == 'subscribe':
                self.logger.info('{} correctly subscribed to {}'.format(self.name, self.system_info_topic),
                                 resource='SystemConsumer')
        except Exception as e:
            self.logger.exception(e)

    @class_fetch_exceptions(publish_error=False, is_context=False)
    def _generic_event_callback_wrapper(self, event: Event):
        self.logger.info('{} received {} event with payload: {} at time: {}'
                         .format(self.name, event, event.payload,
                                 datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d_%H:%M:S')),
                         resource='SystemConsumer')
        callback = self.event_switcher[event.type]['callback']
        if callback is not None:
            self.logger.debug('Calling generic callback with context: {}'.format(self.callbacks_context),
                              resource='SystemConsumer')
            callback(event, context=self.callbacks_context)

    @class_fetch_exceptions(publish_error=False, is_context=False)
    def _system_status_changed_event_callback_wrapper(self, event: SystemStatusChangedEvent):
        self.logger.info('SystemStatusChangedEvent received with status: {} at time: {}'
                         .format(event.system_status,
                                 datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d_%H:%M:S')),
                         resource='SystemConsumer')
        callback = self.event_switcher[event.type]['callback']
        if callback is not None:
            self.logger.debug('Calling system_status_changed callback with context: {}'.format(self.callbacks_context),
                              resource='SystemConsumer')
            callback(event, context=self.callbacks_context)

    @class_fetch_exceptions(publish_error=False, is_context=False)
    def _resource_status_changed_event_callback_wrapper(self, event: ResourceStatusChangedEvent):
        self.logger.info('ResourceStatusChangedEvent received from resource: {} with status: {} at time: {}'
                         .format(event.resource_name, event.resource_status,
                                 datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d_%H:%M:S')),
                         resource='SystemConsumer')
        callback = self.event_switcher[event.type]['callback']
        if callback is not None:
            self.logger.debug('Calling resource_status_changed callback with context: {}'
                              .format(self.callbacks_context), resource='SystemConsumer')
            callback(event, context=self.callbacks_context)

    @class_fetch_exceptions(publish_error=False, is_context=False)
    def _prepare_new_run_event_callback_wrapper(self, event: PrepareNewRunEvent):
        self.logger.info('PrepareNewRunEvent received for resource {} at time: {}'
                         .format(event.new_run_config,
                                 datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d_%H:%M:S')),
                         resource='SystemConsumer')
        callback = self.event_switcher[event.type]['callback']
        if callback is not None:
            self.logger.debug('Calling prepare_new_run callback with context: {}'.format(self.callbacks_context),
                              resource='SystemConsumer')
            callback(event, context=self.callbacks_context)

    @class_fetch_exceptions(publish_error=False, is_context=False)
    def _start_run_event_callback_wrapper(self, event: StartRunEvent):
        self.logger.info('StartRunEvent received with run_code {} at time: {}'
                         .format(event.run_code,
                                 datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d_%H:%M:S')),
                         resource='SystemConsumer')
        callback = self.event_switcher[event.type]['callback']
        if callback is not None:
            self.logger.debug('Calling start_run callback with context: {}'.format(self.callbacks_context),
                              resource='SystemConsumer')
            callback(event, context=self.callbacks_context)

    @class_fetch_exceptions(publish_error=False, is_context=False)
    def _stats_updated_event_callback_wrapper(self, event: StatsUpdateEvent):
        self.logger.info('StatsUpdatedEvent received with run_code: {} stat_group: {} and stat_property: {} at time: {}'
                         .format(event.run_code, event.stat_group, event.stat_property,
                                 datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d_%H:%M:S')),
                         resource='SystemConsumer')
        callback = self.event_switcher[event.type]['callback']
        if callback is not None:
            self.logger.debug('Calling stats_updated callback with context: {}'.format(self.callbacks_context),
                              resource='SystemConsumer')
            callback(event, context=self.callbacks_context)

    @class_fetch_exceptions(publish_error=False, is_context=False)
    def _scheduling_started_event_callback_wrapper(self, event: SchedulingStartedEvent):
        self.logger.info('SchedulingStartedEvent received for phase: {} with task_to_generate: {} and'
                         ' run_config: {} at time: {}'
                         .format(event.phase, event.task_to_generate, event.task_to_schedule_config,
                                 datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d_%H:%M:S')),
                         resource='SystemConsumer')
        callback = self.event_switcher[event.type]['callback']
        if callback is not None:
            self.logger.debug('Calling scheduling_started callback with context: {}'.format(self.callbacks_context),
                              resource='SystemConsumer')
            callback(event, context=self.callbacks_context)

    @class_fetch_exceptions(publish_error=False, is_context=False)
    def _trajectory_completed_event_callback_wrapper(self, event: TrajectoryCompletedEvent):
        self.logger.info('TrajectoryCompletedEvent received with trajectory_id: {} at time: {}'
                         .format(event.trajectory_id,
                                 datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d_%H:%M:S')),
                         resource='SystemConsumer')
        callback = self.event_switcher[event.type]['callback']
        if callback is not None:
            self.logger.debug('Calling trajectory_completed callback with context: {}'.format(self.callbacks_context),
                              resource='SystemConsumer')
            callback(event, context=self.callbacks_context)

    @class_fetch_exceptions(publish_error=False, is_context=False)
    def _scheduling_completed_event_callback_wrapper(self, event: SchedulingCompletedEvent):
        self.logger.info('SchedulingCompletedEvent received for phase: {} with task_scheduled: {} at time: {}'
                         .format(event.phase, event.task_scheduled,
                                 datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d_%H:%M:S')),
                         resource='SystemConsumer')
        callback = self.event_switcher[event.type]['callback']
        if callback is not None:
            self.logger.debug('Calling scheduling_completed callback with context: {}'.format(self.callbacks_context),
                              resource='SystemConsumer')
            callback(event, context=self.callbacks_context)

    @class_fetch_exceptions(publish_error=False, is_context=False)
    def _execution_completed_event_callback_wrapper(self, event: ExecutionCompletedEvent):
        self.logger.info('ExecutionCompletedEvent received for phase: {} with task_executed: {} at time: {}'
                         .format(event.phase, event.task_executed,
                                 datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d_%H:%M:S')),
                         resource='SystemConsumer')
        callback = self.event_switcher[event.type]['callback']
        if callback is not None:
            self.logger.debug('Calling execution_completed callback with context: {}'.format(self.callbacks_context),
                              resource='SystemConsumer')
            callback(event, context=self.callbacks_context)

    @class_fetch_exceptions(publish_error=False, is_context=False)
    def _run_completed_event_callback_wrapper(self, event: RunCompletedEvent):
        self.logger.info('RunCompletedEvent received with run_code: {} at time: {}'
                         .format(event.run_code,
                                 datetime.fromtimestamp(event.timestamp).strftime('%Y-%m-%d_%H:%M:S')),
                         resource='SystemConsumer')
        callback = self.event_switcher[event.type]['callback']
        if callback is not None:
            self.logger.debug('Calling run_completed callback with context: {}'.format(self.callbacks_context),
                              resource='SystemConsumer')
            callback(event, context=self.callbacks_context)
