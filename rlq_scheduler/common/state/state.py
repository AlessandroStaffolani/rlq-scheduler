import numpy as np
import json
from copy import deepcopy

import torch

from rlq_scheduler.common.config_helper import GlobalConfigHelper, RunConfigHelper


def generate_state_from_features(features):
    """
    Generate the state of the environment from features.
    Parameters
    ----------
    features: list
        list of dictionary, where every dictionary can be:
        1. a single property `{ value: <value> }` which is added to the features vector as it is
        2. a more complex dictionary with 3 properties which requires to build a dummie variable:
         `value: <value>`, `is_dummy: <bool>` and `possible_value: <number>`.
         `value` indicates the index of the variable to assign to 1, while `possible_values` indicates the number of
         possible values of the variable, its length
    as_tensor: bool
        if True the result is a torch.tensor
    Returns
    -------
    nd.array | torch.tensor
        a numpy array with the features
    """
    features_vector = prepare_features_vector(features)
    state_array = np.array(features_vector)
    state_array = np.reshape(state_array, (-1, 1))
    return state_array


def state_to_tensor(state: np.ndarray, device='cpu') -> torch.tensor:
    return torch.from_numpy(state).float().to(device=device)


def prepare_features_vector(features):
    """
    Create the features values from the feature description, where each feature is a dictionary with
    two possible structure:
        1. a single property `{ value: <value> }` which is added to the features vector as it is
        2. a more complex dictionary with 3 properties which requires to build a dummie variable:
         `value: <value>`, `is_dummy: <bool>` and `possible_value: <number>`.
         `value` indicates the index of the variable to assign to 1, while `possible_values` indicates the number of
         possible values of the variable, its length
    Parameters
    ----------
    features: list
        list of features
    Returns
    -------
    list
        a list with the values gathered from the features passed
    Examples
    --------
    The state features list should have this structure
    ```
    features = [
        {
            'value': 1,
            'is_dummy': True,
            'possible_values': 4
         },
        {
            'value': 12
        },
        {
            'value': 7
        },
        {
            'value': 18
        }
        ]
    ```
    The result will be:
    ```
    features_values = [0 1 0 0 12 7 18]
    ```
    """
    features_values = []
    for feature in features:
        if feature['type'] == 'array':
            if 'is_dummy' in feature and feature['is_dummy']:
                for i in range(feature['possible_values']):
                    features_values.append(1 if i == feature['value'] else 0)
            else:
                features_values.append(feature['value'] if feature['value'] is not None else 0)
        elif feature['type'] == 'budget':
            features_values.append(feature['value'] if feature['value'] is not None else 0)

    return features_values


class Features(object):

    def __init__(self,
                 global_config: GlobalConfigHelper,
                 run_config: RunConfigHelper,
                 worker_classes=None,
                 task_classes=None,
                 features=None):
        self.global_config: GlobalConfigHelper = global_config
        self.run_config: RunConfigHelper = run_config
        self.features_config = features if features is not None else self.run_config.state_features()
        self.worker_classes = worker_classes if worker_classes is not None else []
        self.task_classes = task_classes if task_classes is not None else []
        self._features_names = []
        self._init_features()

    def _init_features(self):
        for feature_name, feature_conf in self.features_config.items():
            if feature_conf['type'] == 'array':
                self._init_array_feature(feature_conf, feature_name)
            elif feature_conf['type'] == 'budget':
                self._init_budget_feature(feature_conf, feature_name)
            else:
                raise ValueError(f'feature {feature_name} has an unsupported type {feature_conf["type"]}')

    def _init_array_feature(self, feature_conf, feature_name):
        is_global = feature_conf['is_global']
        if feature_conf['is_dummy']:
            if isinstance(feature_conf['values'], str):
                possible_values = len(self._get_feature_values(feature_conf['values']))
                if feature_name == 'action':
                    if self.run_config.is_expandable_pool_enabled() is True:
                        possible_values *= 2
            else:
                possible_values = feature_conf['values']
            attr_value = {'value': None, 'is_dummy': True, 'possible_values': possible_values, 'is_global': is_global}
        else:
            attr_value = {'is_dummy': False}
            values = self._get_feature_values(feature_conf['values'])
            for val in values:
                attr_value[val] = {'value': None}
        attr_value['is_worker_related'] = feature_conf['is_worker_related']
        attr_value['type'] = feature_conf['type']
        attr_value['is_global'] = is_global
        self._features_names.append(feature_name)
        setattr(self, feature_name, attr_value)

    def _init_budget_feature(self, feature_conf, feature_name):
        attr_value = {
            'max': feature_conf['max'],
            'min': feature_conf['min'],
            'normalized': feature_conf['normalized'],
            'type': feature_conf['type'],
            'is_global': feature_conf['is_global']
        }
        if attr_value['normalized'] is True:
            attr_value['value'] = normalize_value(feature_conf['value'],
                                                  v_min=feature_conf['min'],
                                                  v_max=feature_conf['max'])
        else:
            attr_value['value'] = feature_conf['value']
        self._features_names.append(feature_name)
        setattr(self, feature_name, attr_value)

    def _get_feature_values(self, value_types):
        switcher = {
            'worker_classes': self.worker_classes,
            'task_classes': self.task_classes
        }
        if value_types in switcher:
            return switcher[value_types]
        else:
            raise AttributeError('Feature values is not allowed. You should use one of {}'.format(switcher.keys()))

    def set_value(self, feature, value, sub_feature=None):
        feature = getattr(self, feature, None)
        if feature is not None:
            if feature['type'] == 'array':
                if feature['is_dummy']:
                    feature['value'] = value
                else:
                    if sub_feature is not None:
                        feature[sub_feature]['value'] = value
                    else:
                        raise AttributeError('Requested non dummy feature but sub_feature is None')
            elif feature['type'] == 'budget':
                if 'normalized' in feature and feature['normalized'] is True:
                    feature['value'] = normalize_value(value, v_min=feature['min'], v_max=feature['max'])
                else:
                    feature['value'] = value

    def get_feature(self, feature, sub_feature=None):
        f = getattr(self, feature, None)
        if f is None:
            return None
        if f['type'] == 'array':
            if 'is_dummy' in f and f['is_dummy']:
                return f
            else:
                if sub_feature is not None and sub_feature in f:
                    return f[sub_feature]
                else:
                    return f
        elif f['type'] == 'budget':
            return f

    def get_all(self, populate=True):
        features = {}
        for name in self._features_names:
            features[name] = self.get_feature(name)
        if populate:
            return features
        else:
            return self._features_names

    def get_workers_features_name(self, populate=True):
        names = []
        features = {}
        for name in self._features_names:
            feature = self.get_feature(name)
            if feature['is_worker_related']:
                features[name] = feature
                names.append(name)
        if populate:
            return features
        else:
            return names

    def get_global_feature_names(self, populate=True):
        names = []
        features = {}
        for name in self._features_names:
            feature = self.get_feature(name)
            if feature['is_global']:
                features[name] = feature
                names.append(name)
        if populate:
            return features
        else:
            return names

    def get_non_global_feature_names(self, populate=True):
        names = []
        features = {}
        for name in self._features_names:
            feature = self.get_feature(name)
            if not feature['is_global']:
                features[name] = feature
                names.append(name)
        if populate:
            return features
        else:
            return names

    def as_array(self):
        features = []
        for name in self._features_names:
            feature = deepcopy(self.get_feature(name))
            if feature['type'] == 'array':
                del feature['is_worker_related']
                if 'is_dummy' in feature and feature['is_dummy']:
                    features.append(feature)
                else:
                    for k, val in feature.items():
                        if k != 'is_dummy' and k != 'type' and k != 'is_global':
                            features.append({'value': val['value'], 'type': feature['type']})
            elif feature['type'] == 'budget':
                features.append(feature)
        return features

    def to_state(self):
        return generate_state_from_features(self.as_array())

    def size(self):
        size = 0
        for name in self._features_names:
            feature = self.get_feature(name)
            if feature['type'] == 'array':
                if 'is_dummy' in feature and feature['is_dummy']:
                    size += feature['possible_values']
                else:
                    for k, _ in feature.items():
                        if k != 'is_dummy' and k != 'is_worker_related' and k != 'type' and k != 'is_global':
                            size += 1
            elif feature['type'] == 'budget':
                size += 1
        return size

    def keys(self):
        return self.get_all().keys()

    def items(self):
        return self.get_all().items()

    def __len__(self):
        return len(self._features_names)

    def __str__(self):
        return '<Features number={} features={}>'.format(len(self), self.get_all())

    def to_json(self):
        features = self.get_all()
        return json.dumps(features)


def normalize_value(value, v_min, v_max):
    return max(v_min, (value - v_min) / (v_max - v_min))
