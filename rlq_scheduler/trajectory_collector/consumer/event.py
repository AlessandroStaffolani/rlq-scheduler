import json

from enum import Enum
from datetime import datetime


class EventType(Enum):
    GENERAL = 'none'
    EVENT = 'event'
    TASK_EVENT = 'task-event'
    TASK_SENT = 'task-sent'
    TASK_FAILED = 'task-failure'
    TASK_RECEIVED = 'task-received'
    TASK_RECEIVED_TASK_BROKER = 'task-received-task-broker'
    TASK_RECEIVED_WORKER = 'task-received-worker'
    TASK_SUCCEEDED = 'task-succeeded'
    TASK_REJECTED = 'task-rejected'
    WORKER_EVENT = 'worker-event'
    WORKER_ONLINE = 'worker-online'
    WORKER_OFFLINE = 'worker-offline'
    WORKER_HEARTBEAT = 'worker-heartbeat'
    LOG = 'log'


class Event:

    def __init__(self, message, event_type: EventType, timestamp=None, **kwargs):
        self.timestamp = timestamp or datetime.now()
        self.type = event_type
        self.message = message
        self.extra = kwargs
        self.extra['event_type'] = self.type.value

    def __str__(self):
        value = f'timestamp: {self.timestamp.strftime("%d-%m-%Y %H:%M:%S")}'
        value += f' | type: {self.type.value}'
        value += f' | message: {self.message}'
        value += f''.join([f' | {k}: {v}' for k, v in self.extra.items()])
        return value

    def log_str(self, long=True):
        value = f'type: {self.type.value}'
        value += f' | message: {self.message}'
        if long:
            value += f''.join([f' | {k}: {v}' for k, v in self.extra.items()])
        return value

    def json(self):
        message = {
            'timestamp': self.timestamp.timestamp(),
            'type': self.type.value,
            'message': self.message,
            'extra': self.extra
        }
        return json.dumps(message)

    @staticmethod
    def from_json(json_message):
        message = json.loads(json_message)
        return Event(
            message=message['message'],
            event_type=EventType(message['type']),
            timestamp=datetime.fromtimestamp(message['timestamp']),
            **message['extra']
        )
