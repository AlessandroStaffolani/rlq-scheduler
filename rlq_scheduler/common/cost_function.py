import re

import pandas as pd
from sklearn.linear_model import LinearRegression

from rlq_scheduler.common.config_helper import GlobalConfigHelper, RunConfigHelper
from rlq_scheduler.common.exceptions import NoRunConfigException
from rlq_scheduler.common.utils.filesystem import get_absolute_path


def get_value_from_kube_resource_value(value):
    return float(re.sub(r'[^0-9]', '', value))


class ExecutionCostCalculator:

    def __init__(self, global_config: GlobalConfigHelper):
        self.global_config: GlobalConfigHelper = global_config
        self.run_config: RunConfigHelper = None
        self.regression_model: LinearRegression = None
        self.cost_functions = {
            'market-based': self._market_based,
            'value-based': self._value_based
        }

    def init_regression_model(self):
        if self.run_config is not None:
            train_data_path = get_absolute_path(self.run_config.execution_cost_function_train_data())
            data = pd.read_csv(train_data_path)
            x = data[['cpu', 'ram', 'disk']]
            y = data[['cost']]
            self.regression_model = LinearRegression()
            self.regression_model.fit(x, y)
        else:
            raise NoRunConfigException('ExecutionCostCalculator')

    def get_execution_cost(self, worker_class, is_internal=True) -> float:
        if self.run_config is not None:
            cost_func_type = self.run_config.execution_cost_function_type()
            if cost_func_type in self.cost_functions:
                cost = self.cost_functions[cost_func_type](worker_class)
                if is_internal is True:
                    return cost
                else:
                    return cost * 2
            else:
                raise AttributeError('Execution cost function type "{}" not valid.'.format(cost_func_type))
        else:
            raise NoRunConfigException('ExecutionCostCalculator')

    def _market_based(self, worker_class) -> float:
        worker_class_resources = self.global_config.worker_class_resources_limits(worker_class)
        worker_class_replicas = self.global_config.worker_class_replicas(worker_class)
        if self.regression_model is not None:
            cpu = get_value_from_kube_resource_value(worker_class_resources['cpu']) / 1000
            ram = get_value_from_kube_resource_value(worker_class_resources['memory']) / 1000
            disk = get_value_from_kube_resource_value(worker_class_resources['disk']) / 1000
            cost = self.regression_model.predict([[cpu, ram, disk]])[0][0]
            return cost * worker_class_replicas

    def _value_based(self, worker_class):
        return self.run_config.worker_class_cost_per_usage(worker_class, internal_cost=True)
