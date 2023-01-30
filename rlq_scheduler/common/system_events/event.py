import json
import time
from copy import deepcopy
from enum import Enum

from rlq_scheduler.common.run_config import RunConfig
from rlq_scheduler.common.system_status import SystemStatus, ResourceStatus


class SystemEvent(str, Enum):
    GENERIC = "GENERIC"
    SYSTEM_STATUS_CHANGED = "SYSTEM_STATUS_CHANGED"
    RESOURCE_STATUS_CHANGED = "RESOURCE_STATUS_CHANGED"
    PREPARE_NEW_RUN = "PREPARE_NEW_RUN"
    START_RUN = "START_RUN"
    STATS_UPDATED = "STATS_UPDATED"
    SCHEDULING_STARTED = "SCHEDULING_STARTED"
    TRAJECTORY_COMPLETED = "TRAJECTORY_COMPLETED"
    SCHEDULING_COMPLETED = "SCHEDULING_COMPLETED"
    EXECUTION_COMPLETED = "EXECUTION_COMPLETED"
    RUN_COMPLETED = "RUN_COMPLETED"


class RunPhase(str, Enum):
    WAIT = "WAIT"
    BOOTSTRAP = "BOOTSTRAP"
    RUN = "RUN"


class Event:

    def __init__(self, event_type: SystemEvent = SystemEvent.GENERIC, payload=None, timestamp=None):
        self.type: SystemEvent = event_type
        self.payload = payload
        self.timestamp = time.time() if timestamp is None else timestamp

    def __str__(self):
        return '<Event type={} >'.format(self.type)

    def to_dict(self):
        return {
            'type': self.type,
            'payload': self.payload,
            'timestamp': self.timestamp
        }

    def to_json(self, cls=None):
        return json.dumps(self.to_dict(), cls=cls)

    @staticmethod
    def deserialize_payload(payload):
        return payload

    @staticmethod
    def from_json(json_event):
        parsed = json.loads(json_event)
        event_type = SystemEvent(parsed['type'])
        timestamp = parsed['timestamp']
        if event_type in EVENT_DESERIALIZATION_SWITCHER:
            event_class = EVENT_DESERIALIZATION_SWITCHER[event_type]
            if event_type == SystemEvent.GENERIC:
                payload = {
                    'event_type': event_type,
                    'payload': parsed['payload'],
                    'timestamp': timestamp
                }
            else:
                payload = event_class.deserialize_payload(parsed['payload'])
                payload['timestamp'] = timestamp
            return event_class(**payload)
        else:
            raise AttributeError('event_type of the json event is not available')


class SystemStatusChangedEvent(Event):

    def __init__(self, system_status: SystemStatus, timestamp=None, **kwargs):
        self.system_status = system_status
        self.extras = kwargs if len(kwargs) > 0 else None
        super(SystemStatusChangedEvent, self).__init__(
            event_type=SystemEvent.SYSTEM_STATUS_CHANGED,
            payload={
                'system_status': self.system_status,
                'extras': self.extras
            },
            timestamp=timestamp
        )

    def __str__(self):
        return '<Event type={} system_status={} >'.format(self.type, self.system_status)

    @staticmethod
    def deserialize_payload(payload):
        new_payload = deepcopy(payload)
        new_payload['system_status'] = SystemStatus(payload['system_status'])
        return new_payload


class ResourceStatusChangedEvent(Event):

    def __init__(self, resource_name: str, resource_status: ResourceStatus, timestamp=None, **kwargs):
        self.resource_name = resource_name
        self.resource_status = resource_status
        self.extras = kwargs if len(kwargs) > 0 else None
        super(ResourceStatusChangedEvent, self).__init__(
            event_type=SystemEvent.RESOURCE_STATUS_CHANGED,
            payload={
                'resource_name': self.resource_name,
                'resource_status': self.resource_status,
                'extras': self.extras
            },
            timestamp=timestamp
        )

    def __str__(self):
        return '<Event type={} resource_name={} resource_status={} >'\
            .format(self.type, self.resource_name, self.resource_status)

    @staticmethod
    def deserialize_payload(payload):
        new_payload = deepcopy(payload)
        new_payload['resource_status'] = ResourceStatus(payload['resource_status'])
        return new_payload


class PrepareNewRunEvent(Event):

    def __init__(self, new_run_config: RunConfig, timestamp=None, **kwargs):
        self.new_run_config = new_run_config
        self.extras = kwargs if len(kwargs) > 0 else None
        super(PrepareNewRunEvent, self).__init__(
            event_type=SystemEvent.PREPARE_NEW_RUN,
            payload={
                'new_run_config': new_run_config.to_dict(),
                'extras': self.extras
            },
            timestamp=timestamp
        )

    def __str__(self):
        return '<Event type={} new_run_config={} >'.format(self.type, self.new_run_config)

    @staticmethod
    def deserialize_payload(payload):
        new_payload = deepcopy(payload)
        new_payload['new_run_config'] = RunConfig.from_dict(payload['new_run_config'])
        return new_payload


class StartRunEvent(Event):

    def __init__(self, run_code, timestamp=None, **kwargs):
        self.run_code = run_code
        self.extras = kwargs if len(kwargs) > 0 else None
        super(StartRunEvent, self).__init__(
            event_type=SystemEvent.START_RUN,
            payload={
                'run_code': self.run_code,
                'extras': self.extras
            },
            timestamp=timestamp
        )

    def __str__(self):
        return '<Event type={} run_code={} >'.format(self.type, self.run_code)


class StatsUpdateEvent(Event):

    def __init__(self, run_code, stat_group, stat_property=None, timestamp=None, **kwargs):
        self.run_code = run_code
        self.stat_group = stat_group
        self.stat_property = stat_property
        self.extras = kwargs if len(kwargs) > 0 else None
        super(StatsUpdateEvent, self).__init__(
            event_type=SystemEvent.STATS_UPDATED,
            payload={
                'run_code': self.run_code,
                'stat_group': self.stat_group,
                'stat_property': self.stat_property,
                'extras': self.extras
            },
            timestamp=timestamp
        )

    def __str__(self):
        return '<Event type={} run_code={} stat_group={} stat_property={}>' \
            .format(self.type, self.run_code, self.stat_group, self.stat_property)


class SchedulingStartedEvent(Event):

    def __init__(self, phase: RunPhase, task_to_generate, task_to_schedule_config, timestamp=None, **kwargs):
        self.phase = phase
        self.task_to_generate = task_to_generate
        self.task_to_schedule_config = task_to_schedule_config
        self.extras = kwargs if len(kwargs) > 0 else None
        super(SchedulingStartedEvent, self).__init__(
            event_type=SystemEvent.SCHEDULING_STARTED,
            payload={
                'phase': self.phase,
                'task_to_generate': self.task_to_generate,
                'task_to_schedule_config': self.task_to_schedule_config,
                'extras': self.extras
            },
            timestamp=timestamp
        )

    @staticmethod
    def deserialize_payload(payload):
        new_payload = deepcopy(payload)
        new_payload['phase'] = RunPhase(payload['phase'])
        return new_payload

    def __str__(self):
        return '<Event type={} phase={} task_to_generate={} task_to_schedule_config={}>' \
            .format(self.type, self.phase, self.task_to_generate, self.task_to_schedule_config)


class TrajectoryCompletedEvent(Event):

    def __init__(self, trajectory_id, timestamp=None, **kwargs):
        self.trajectory_id = trajectory_id
        self.extras = kwargs if len(kwargs) > 0 else None
        super(TrajectoryCompletedEvent, self).__init__(
            event_type=SystemEvent.TRAJECTORY_COMPLETED,
            payload={
                'trajectory_id': self.trajectory_id,
                'extras': self.extras
            },
            timestamp=timestamp
        )

    def __str__(self):
        return '<Event type={} trajectory_id={} >'.format(self.type, self.trajectory_id)


class SchedulingCompletedEvent(Event):

    def __init__(self, phase: RunPhase, task_scheduled, timestamp=None, **kwargs):
        self.phase = phase
        self.task_scheduled = task_scheduled
        self.extras = kwargs if len(kwargs) > 0 else None
        super(SchedulingCompletedEvent, self).__init__(
            event_type=SystemEvent.SCHEDULING_COMPLETED,
            payload={
                'phase': self.phase,
                'task_scheduled': self.task_scheduled,
                'extras': self.extras
            },
            timestamp=timestamp
        )

    @staticmethod
    def deserialize_payload(payload):
        new_payload = deepcopy(payload)
        new_payload['phase'] = RunPhase(payload['phase'])
        return new_payload

    def __str__(self):
        return '<Event type={} phase={} task_scheduled={} >'.format(self.type, self.phase, self.task_scheduled)


class ExecutionCompletedEvent(Event):

    def __init__(self, phase: RunPhase, task_executed, timestamp=None, **kwargs):
        self.phase = phase
        self.task_executed = task_executed
        self.extras = kwargs if len(kwargs) > 0 else None
        super(ExecutionCompletedEvent, self).__init__(
            event_type=SystemEvent.EXECUTION_COMPLETED,
            payload={
                'phase': self.phase,
                'task_executed': self.task_executed,
                'extras': self.extras
            },
            timestamp=timestamp
        )

    @staticmethod
    def deserialize_payload(payload):
        new_payload = deepcopy(payload)
        new_payload['phase'] = RunPhase(payload['phase'])
        return new_payload

    def __str__(self):
        return '<Event type={} phase={} task_executed={} >'.format(self.type, self.phase, self.task_executed)


class RunCompletedEvent(Event):

    def __init__(self, run_code, timestamp=None, **kwargs):
        self.run_code = run_code
        self.extras = kwargs if len(kwargs) > 0 else None
        super(RunCompletedEvent, self).__init__(
            event_type=SystemEvent.RUN_COMPLETED,
            payload={
                'run_code': self.run_code,
                'extras': self.extras
            },
            timestamp=timestamp
        )

    def __str__(self):
        return '<Event type={} run_code={} >'.format(self.type, self.run_code)


EVENT_DESERIALIZATION_SWITCHER = {
    SystemEvent.GENERIC: Event,
    SystemEvent.SYSTEM_STATUS_CHANGED: SystemStatusChangedEvent,
    SystemEvent.RESOURCE_STATUS_CHANGED: ResourceStatusChangedEvent,
    SystemEvent.PREPARE_NEW_RUN: PrepareNewRunEvent,
    SystemEvent.START_RUN: StartRunEvent,
    SystemEvent.STATS_UPDATED: StatsUpdateEvent,
    SystemEvent.SCHEDULING_STARTED: SchedulingStartedEvent,
    SystemEvent.TRAJECTORY_COMPLETED: TrajectoryCompletedEvent,
    SystemEvent.SCHEDULING_COMPLETED: SchedulingCompletedEvent,
    SystemEvent.EXECUTION_COMPLETED: ExecutionCompletedEvent,
    SystemEvent.RUN_COMPLETED: RunCompletedEvent,
}
