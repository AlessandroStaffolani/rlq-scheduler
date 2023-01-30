import json
from enum import Enum
from logging import Logger
from threading import RLock

from rlq_scheduler.common.backends.backend_factory import get_backend_adapter
from rlq_scheduler.common.backends.redis_backend import RedisBufferBackend
from rlq_scheduler.common.config_helper import RunConfigHelper, GlobalConfigHelper
from rlq_scheduler.common.state.state import Features


class StorageMode(str, Enum):
    LOCAL = 'local'
    SHARED = 'shared'


def init_backend(config: GlobalConfigHelper, backed_type, logger: Logger):
    backend_class = get_backend_adapter(config.backend_adapter(), backed_type=backed_type)
    return backend_class(config=config.backend_config(), logger=logger)


class StateBuilder:

    def __init__(
            self,
            global_config: GlobalConfigHelper,
            logger: Logger,
            is_workers_load_local=False
    ):
        self.global_config: GlobalConfigHelper = global_config
        self.run_config: RunConfigHelper = None
        self.logger: Logger = logger
        self.mode: StorageMode = StorageMode(self.global_config.state_builder_mode())
        self.backend: RedisBufferBackend = RedisBufferBackend(0,
                                                              config=self.global_config.backend_config(),
                                                              logger=logger)

        self.state_features: Features = None
        self.workers_pool_info = {
            'pool_total': 0,
            'workers': {}
        }
        self.workers_load = {worker: 0 for worker in self.global_config.available_worker_classes()}
        self.workers_capacity_utilization = {worker: 0 for worker in self.global_config.available_worker_classes()}
        self.pool_size = sum([self.global_config.worker_class_replicas(worker) for worker in
                              self.global_config.available_worker_classes()])
        self.is_workers_load_local = is_workers_load_local
        self.features_mapping = {
            'pool_availability': self.update_pool_availability_feature,
            'task_class_type': self.update_task_class_type_feature,
            'resource_usage': self.update_time_window_feature,
            'task_frequency': self.update_time_window_feature,
            'action': self.update_action_feature,
            'pool_load': self.update_pool_load_feature,
        }
        self.resource_lock = RLock()

    def set_run_config(self, run_config: RunConfigHelper):
        self.run_config = run_config
        self.backend.size = self.run_config.state_time_window()
        self.workers_load = {worker: 0 for worker in self.global_config.available_worker_classes()}
        self.workers_pool_info = {
            'pool_total': 0,
            'workers': {}
        }

    def set_state_features(self, features: Features):
        self.state_features = features

    def update_pool_info(self, pool_info):
        with self.resource_lock:
            self.workers_pool_info = pool_info
            return self._store_data(key=self.global_config.state_builder_worker_state_key(),
                                    data=json.dumps(self.workers_pool_info))

    def update_pool_availability_feature(self, features: Features = None, *args, **kwargs):
        if self.state_features is not None:
            with self.resource_lock:
                pool_info = self.workers_pool_info
            if self.mode == StorageMode.SHARED:
                pool_info = json.loads(self.backend.get(key=self.global_config.state_builder_worker_state_key()))
            with self.resource_lock:
                for worker, info in pool_info['workers'].items():
                    value = info['available_workers'] / pool_info['pool_total']

                    self._update_single_feature(
                        feature_name='pool_availability',
                        value=value,
                        sub_feature=worker,
                        features=features
                    )
                return self._store_data(key=self.global_config.state_builder_state_key(),
                                        data=self.state_features.to_json())
        else:
            self.logger.error('Requested update of features, but they have not been initialized',
                              resource='StateBuilder')
            return False

    def update_action_feature(self, action_index, features: Features = None, *args, **kwargs):
        if self.state_features is not None and self.run_config is not None:
            with self.resource_lock:
                self._update_single_feature(
                    feature_name='action',
                    value=action_index,
                    features=features
                )
                return self._store_data(key=self.global_config.state_builder_state_key(),
                                        data=self.state_features.to_json())
        else:
            self.logger.error(f'state features and run_config must be initialized', resource='StateBuilder')

    def update_task_class_type_feature(self, task_class, features: Features = None, *args, **kwargs):
        if self.state_features is not None and self.run_config is not None:
            self.logger.debug('Task class index = {}'.format(self.run_config.task_class_index(task_class)),
                              resource='StateBuilder')
            with self.resource_lock:
                self._update_single_feature(
                    feature_name='task_class_type',
                    value=self.run_config.task_class_index(task_class),
                    features=features
                )
                return self._store_data(key=self.global_config.state_builder_state_key(),
                                        data=self.state_features.to_json())
        else:
            self.logger.error(f'state features and run_config must be initialized', resource='StateBuilder')

    def update_budget_feature(self, feature_name, value_to_subtract, features: Features = None):
        if self.state_features is not None and self.run_config is not None:
            with self.resource_lock:
                current_value = self.state_features.get_feature(feature_name)['value']
                self._update_single_feature(feature_name,
                                            value=current_value - value_to_subtract,
                                            features=features)
                self.logger.debug(f'Update budget for {feature_name} current budget is '
                                  f'{self.state_features.get_feature(feature_name)["value"]}', resource='StateBuilder')
                return self._store_data(key=self.global_config.state_builder_state_key(),
                                        data=self.state_features.to_json())
        else:
            self.logger.error(f'state features and run_config must be initialized', resource='StateBuilder')

    def update_time_window_feature(self, feature_name, features: Features = None, *args, **kwargs):
        if self.state_features is not None and self.run_config is not None:
            keys = {
                'resource_usage': self.global_config.state_builder_resource_usage_key(),
                'task_frequency': self.global_config.state_builder_task_frequency_key()
            }
            all_classes = {
                'resource_usage': self.run_config.available_worker_classes(),
                'task_frequency': self.run_config.available_tasks_classes()
            }
            key = keys[feature_name]
            feature_classes = all_classes[feature_name]
            window_items = self.backend.get_buffer(key=key)
            classes = {}
            for item in window_items:
                if item in classes:
                    classes[item] += 1
                else:
                    classes[item] = 1
            with self.resource_lock:
                for item_class in feature_classes:
                    if item_class not in classes:
                        value = 0
                    else:
                        value = float(classes[item_class] / len(window_items))
                    self._update_single_feature(feature_name, value, sub_feature=item_class, features=features)
                self.logger.debug(f'Update time window feature {feature_name}', resource='StateBuilder')
                return self._store_data(key=self.global_config.state_builder_state_key(),
                                        data=self.state_features.to_json())
        else:
            self.logger.error(f'state features and run_config must be initialized', resource='StateBuilder')

    def update_pool_load_feature(self, features: Features = None, *args, **kwargs):
        if self.state_features is not None and self.run_config is not None:
            if self.is_workers_load_local:
                # no need to get the load from the shared memory
                pool_load = self.workers_load
            else:
                # get the load from the shared memory
                pool_load = json.loads(self.backend.get(key=self.global_config.state_builder_pool_load_key()))
            pool_load_size = 0
            self.logger.debug(f'Pool load = {pool_load}', resource='StateBuilder')
            if not self.run_config.is_replicas_normalization():
                for _, load in pool_load.items():
                    pool_load_size += load
            for worker_class in self.run_config.available_worker_classes():
                value = 0
                if self.run_config.is_replicas_normalization():
                    worker_class_replicas = self.global_config.worker_class_replicas(worker_class)
                    value = float(pool_load[worker_class] / worker_class_replicas)
                else:
                    if pool_load_size > 0:
                        value = float(pool_load[worker_class] / pool_load_size)
                self._update_single_feature(
                    feature_name='pool_load',
                    value=value,
                    sub_feature=worker_class,
                    features=features
                )
            self.logger.debug(f'Updated pool load feature | '
                              f'pool_load feature = {self.state_features.get_feature("pool_load")}',
                              resource='StateBuilder')
            return self._store_data(key=self.global_config.state_builder_state_key(),
                                    data=self.state_features.to_json())
        else:
            self.logger.error(f'state features and run_config must be initialized', resource='StateBuilder')

    def update_global_features(self, task_class, features: Features = None, **kwargs):
        if features is None:
            global_features = self.state_features.get_global_feature_names(populate=False)
        else:
            global_features = features.get_global_feature_names(populate=False)
        self.update_features(global_features, task_class=task_class, features=features, **kwargs)

    def update_non_global_features(self, action_index, features: Features = None, **kwargs):
        if features is None:
            non_global_features = self.state_features.get_non_global_feature_names(populate=False)
        else:
            non_global_features = features.get_non_global_feature_names(populate=False)
        self.update_features(non_global_features, action_index=action_index, features=features, **kwargs)

    def update_features(self, feature_names, features: Features = None, **kwargs):
        for feature_name in feature_names:
            if features is None:
                feature = self.state_features.get_feature(feature_name)
            else:
                feature = features.get_feature(feature_name)
            if feature['type'] != 'budget' and feature_name in self.features_mapping:
                self.features_mapping[feature_name](feature_name=feature_name, features=features, **kwargs)
        self.logger.debug('Updated state features {} using and arguments = {}'
                          .format(feature_names, kwargs),
                          resource='StateBuilder')

    def get_state(self, task_id, task_class, features: Features = None, **kwargs):
        if features is None:
            feature_names = self.state_features.get_all(populate=False)
        else:
            feature_names = features.get_all(populate=False)
        self.update_features(feature_names, features=features, task_id=task_id, task_class=task_class, **kwargs)
        with self.resource_lock:
            return self.state_features.to_state()

    def add_resource_usage_entry(self, worker_class):
        if self.run_config is not None:
            self.backend.push(
                key=self.global_config.state_builder_resource_usage_key(),
                value=worker_class
            )
        else:
            self.logger.error('Trying to add resource usage entry, but run_config is None', resource='StateBuilder')

    def add_task_frequency_entry(self, task_class):
        if self.run_config is not None:
            self.backend.push(
                key=self.global_config.state_builder_task_frequency_key(),
                value=task_class
            )
        else:
            self.logger.error('Trying to add resource usage entry, but run_config is None', resource='StateBuilder')

    def update_pool_load(self, worker_class: str, load_update: int, task_class: str, task_parameters: dict):
        if self.run_config is not None:
            self.workers_load[worker_class] += load_update
            utilization_cost = self._compute_task_utilization_cost(task_class, task_parameters)
            if self.run_config.is_google_traces_mode_enabled():
                speed_factor = self.run_config.worker_class_speed_factor(worker_class)
                self.logger.debug(f'Worker class = {worker_class} | speed factor = {speed_factor} | '
                                  f'utilization cost = {utilization_cost} | '
                                  f'utilization cost scaled = {utilization_cost / speed_factor}')
                utilization_cost /= speed_factor
            if load_update > 0:
                self.workers_capacity_utilization[worker_class] += utilization_cost
            else:
                self.workers_capacity_utilization[worker_class] -= utilization_cost
            if self.workers_capacity_utilization[worker_class] < 0:
                self.workers_capacity_utilization[worker_class] = 0
            self.logger.debug('Updated workers pool load, current values are: {}'.format(self.workers_load))
            self.logger.debug('Updated workers pool utilization cost, current values are: {}'
                              .format(self.workers_capacity_utilization))
        else:
            self.logger.error('Trying to update pool load, but run_config is None', resource='StateBuilder')

    def load_workers_utilization(self):
        worker_utilization = self.backend.get(key=self.global_config.state_builder_pool_utilization_key())
        if worker_utilization is not None:
            return json.loads(worker_utilization)
        else:
            return self.workers_capacity_utilization

    def _compute_task_utilization_cost(self, task_class: str, task_parameters: dict):
        parameters = float(task_parameters['n'])
        if 'd' in task_parameters:
            parameters *= float(task_parameters['d'])
        utilization_constant = self.run_config.task_class_capacity_usage_cost(task_class)
        if self.run_config.is_google_traces_mode_enabled():
            return utilization_constant
        utilization_parameters = self._scale_task_parameters(task_class, parameters)
        utilization_cost = utilization_constant + utilization_parameters
        self.logger.debug(f'Utilization cost: {utilization_cost} | Utilization constant: {utilization_constant} |'
                          f' parameters value: {parameters} |'
                          f' parameters scaled: {utilization_parameters}')
        return utilization_cost

    def _scale_task_parameters(self, task_class: str, parameters_value: float) -> float:
        initial_range = self.run_config.task_class_capacity_usage_parameters_range(task_class)
        final_range = self.run_config.task_class_capacity_usage_delta_range(task_class)
        initial_range_diff = initial_range[1] - initial_range[0]
        final_range_diff = final_range[1] - final_range[0]
        return (((parameters_value - initial_range[0]) * final_range_diff) / initial_range_diff) + final_range[0]

    def upload_pool_load_on_shared_memory(self):
        result_1 = self._store_on_backend(
            key=self.global_config.state_builder_pool_load_key(),
            data=json.dumps(self.workers_load)
        )
        result_2 = self._store_on_backend(
            key=self.global_config.state_builder_pool_utilization_key(),
            data=json.dumps(self.workers_capacity_utilization)
        )
        return result_1 and result_2

    def _update_single_feature(self, feature_name, value, sub_feature=None, features: Features = None):
        if features is None:
            self.state_features.set_value(feature_name, value, sub_feature=sub_feature)
        else:
            features.set_value(feature_name, value, sub_feature=sub_feature)

    def _store_data(self, key, data):
        if self.mode == StorageMode.SHARED:
            result = self._store_on_backend(key=key, data=data)
        else:
            result = True
        return result

    def _store_on_backend(self, key, data):
        result = self.backend.save(key, data)
        if result is True:
            self.logger.debug(f'Updated data with key {key}', resource='StateBuilder')
        else:
            self.logger.error(f'Error while saving data for key {key}', resource='StateBuilder')
        return result
