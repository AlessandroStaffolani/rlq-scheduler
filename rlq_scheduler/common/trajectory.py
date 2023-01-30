import json
import time
import uuid
from copy import deepcopy
from datetime import datetime
from enum import Enum

import numpy as np

from rlq_scheduler.common.utils.encoders import NumpyEncoder


class TrajectoryProperties(str, Enum):
    ID = 'id'
    CREATED_AT = 'created_at'
    STATE = 'state'
    ACTION = 'action'
    CONTEXT = 'context'
    NEXT_STATE = 'next_state'
    REWARD = 'reward'


NUMPY_PROPS = [TrajectoryProperties.STATE, TrajectoryProperties.NEXT_STATE, TrajectoryProperties.CONTEXT]
OBJ_PROPS = [TrajectoryProperties.CREATED_AT]
INT_PROPS = [TrajectoryProperties.ACTION]
FLOAT_PROPS = [TrajectoryProperties.REWARD]


def _dict_keys_as_string(o):
    new_dict = {}
    for prop, value in o.items():
        new_dict[prop.value] = value
    return new_dict


class Trajectory:

    def __init__(self, id=None, state=None, action=None, context=None, next_state=None, reward=None, created_ad=None):
        self._id = id if id is not None else str(uuid.uuid4())
        self._trajectory = {
            TrajectoryProperties.ID: self._id,
            TrajectoryProperties.CREATED_AT: created_ad if created_ad is not None else time.time(),
            TrajectoryProperties.STATE: state if state is not None else None,
            TrajectoryProperties.ACTION: action if action is not None else None,
            TrajectoryProperties.CONTEXT: context if context is not None else None,
            TrajectoryProperties.NEXT_STATE: next_state if next_state is not None else None,
            TrajectoryProperties.REWARD: reward if reward is not None else None
        }

    def id(self):
        return self._id

    def __getitem__(self, name):
        return self._trajectory[TrajectoryProperties(name)]

    def __iter__(self):
        return iter(self._trajectory)

    def keys(self, as_string=False):
        if as_string is True:
            keys = list(self._trajectory.keys())
            keys = [k.value for k in keys]
            return keys
        return self._trajectory.keys()

    def items(self):
        return self._trajectory.items()

    def values(self):
        return self._trajectory.values()

    def state(self):
        return self[TrajectoryProperties.STATE]

    def action(self):
        return self[TrajectoryProperties.ACTION]

    def context(self):
        return self[TrajectoryProperties.CONTEXT]

    def next_state(self):
        return self[TrajectoryProperties.NEXT_STATE]

    def reward(self):
        return self[TrajectoryProperties.REWARD]

    def created_at(self, formated=False, fmt='%d-%m-%Y %H:%M:%S,%f'):
        if formated is True:
            created_at_timestamp = self[TrajectoryProperties.CREATED_AT]
            date = datetime.utcfromtimestamp(created_at_timestamp)
            return date.strftime(fmt)
        else:
            return self[TrajectoryProperties.CREATED_AT]

    def set_property(self, prop, value):
        prop = TrajectoryProperties(prop)
        if prop in NUMPY_PROPS:
            self._trajectory[prop] = np.array(value) if value is not None else None
        elif prop in OBJ_PROPS:
            self._trajectory[prop] = value if value is not None else None
        elif prop in INT_PROPS:
            self._trajectory[prop] = int(value) if value is not None else None
        elif prop in FLOAT_PROPS:
            self._trajectory[prop] = float(value) if value is not None else None
        else:
            self._trajectory[prop] = value

    def set_state(self, state):
        self._trajectory[TrajectoryProperties.STATE] = state

    def set_action(self, action):
        self._trajectory[TrajectoryProperties.ACTION] = action

    def set_context(self, context):
        self._trajectory[TrajectoryProperties.CONTEXT] = context

    def set_next_state(self, next_state):
        self._trajectory[TrajectoryProperties.NEXT_STATE] = next_state

    def set_reward(self, reward):
        self._trajectory[TrajectoryProperties.REWARD] = reward

    def set_trajectory(self, trajectory):
        self._trajectory = trajectory

    def as_dict(self, data_formated=False, keys_as_string=False):
        if data_formated is True:
            t = deepcopy(self._trajectory)
            t[TrajectoryProperties.CREATED_AT] = self.created_at(formated=True)
            if keys_as_string is True:
                return _dict_keys_as_string(t)
            return t
        else:
            if keys_as_string is True:
                return _dict_keys_as_string(self._trajectory)
            return self._trajectory

    def to_plain_dict(self):
        t = deepcopy(self._trajectory)
        t[TrajectoryProperties.STATE] = self[TrajectoryProperties.STATE].tolist() \
            if self[TrajectoryProperties.STATE] is not None else None
        t[TrajectoryProperties.CONTEXT] = self[TrajectoryProperties.CONTEXT].tolist() \
            if self[TrajectoryProperties.CONTEXT] is not None else None
        t[TrajectoryProperties.NEXT_STATE] = self[TrajectoryProperties.NEXT_STATE].tolist() \
            if self[TrajectoryProperties.NEXT_STATE] is not None else None
        return t

    def to_json(self):
        return json.dumps(self._trajectory, cls=NumpyEncoder)

    def is_complete(self, is_context_enabled=False):
        for prop, item in self.as_dict().items():
            if is_context_enabled is True:
                if item is None:
                    return False
            else:
                if prop != TrajectoryProperties.CONTEXT and item is None:
                    return False
        else:
            return True

    @staticmethod
    def from_dict(tra_dict):
        return Trajectory(
            id=tra_dict['id'],
            state=np.array(tra_dict['state']) if tra_dict['state'] is not None else None,
            action=tra_dict['action'],
            context=np.array(tra_dict['context']) if tra_dict['context'] is not None else None,
            next_state=np.array(tra_dict['next_state']) if tra_dict['next_state'] is not None else None,
            reward=tra_dict['reward'],
            created_ad=tra_dict['created_at'] if tra_dict['created_at'] is not None else None,
        )

    @staticmethod
    def from_json(json_string):
        obj = json.loads(json_string)
        return Trajectory.from_dict(obj)

    @staticmethod
    def get_trajectory_properties():
        return [prop.value for prop in TrajectoryProperties]

    @staticmethod
    def deserialize_trajectory_vector(state, from_json=False):
        if from_json is True and state is not None:
            state = json.loads(state)
        return np.array(state) if state is not None else None

    def __str__(self):
        items = deepcopy(self._trajectory)
        created_at = self.created_at(formated=True)
        del items[TrajectoryProperties.CREATED_AT]
        items[TrajectoryProperties.STATE] = np.reshape(items[TrajectoryProperties.STATE], (-1, )) \
            if items[TrajectoryProperties.STATE] is not None else None
        items[TrajectoryProperties.NEXT_STATE] = np.reshape(items[TrajectoryProperties.NEXT_STATE], (-1,)) \
            if items[TrajectoryProperties.NEXT_STATE] is not None else None
        items_to_print = {}
        for prop, value in items.items():
            items_to_print[prop.value] = value
        return '<Trajectory id={} created_at={} items={}>'.format(self._id, created_at, items_to_print)
