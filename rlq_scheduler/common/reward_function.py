import time
from logging import Logger
from copy import deepcopy

from rlq_scheduler.common.config_helper import GlobalConfigHelper, RunConfigHelper
from rlq_scheduler.common.cost_function import ExecutionCostCalculator


class BaseRewardFunction:

    def __init__(
            self,
            global_config: GlobalConfigHelper,
            run_config: RunConfigHelper,
            execution_cost_calculator: ExecutionCostCalculator,
            logger: Logger,
            name: str,
            **kwargs
    ):
        self.logger = logger
        self.global_config: GlobalConfigHelper = global_config
        self.run_config: RunConfigHelper = run_config
        self.name = name
        self.execution_cost_calculator: ExecutionCostCalculator = execution_cost_calculator

    def __str__(self):
        return f'<Reward Function name={self.name} >'

    def _failed_task(self):
        return float(self.run_config.task_failed_penalty())

    def _log_reward_parameters(self, execution_time, execution_cost, waiting_cost, waiting_time):
        self.logger.debug('Reward parameters = {}'.format({
            'execution_time': execution_time,
            'execution_cost': execution_cost,
            'waiting_cost': waiting_cost,
            'waiting_time': waiting_time
        }), resource='RewardFunction')

    def _push_trajectory_extra_info(self,
                                    task_id,
                                    worker_class,
                                    waiting_time,
                                    waiting_cost,
                                    execution_cost,
                                    execution_time,
                                    push_trajectory_extra_info):
        if push_trajectory_extra_info is not None:
            push_trajectory_extra_info(
                trajectory_id=task_id,
                worker_class=worker_class,
                waiting_time=waiting_time,
                waiting_cost=waiting_cost,
                execution_cost=execution_cost,
                execution_time=execution_time
            )

    def _get_execution_cost(self, worker_class, is_internal=True):
        return float(self.execution_cost_calculator.get_execution_cost(
            worker_class=worker_class,
            is_internal=is_internal
        ))

    def _get_waiting_cost(self, task_class):
        return float(self.run_config.task_class_waiting_cost(task_class))

    def _pre_compute(self,
                     task_id: str,
                     task_class: str,
                     worker_class: str,
                     waiting_time: float,
                     execution_time: float,
                     failed: bool,
                     is_internal=True,
                     push_trajectory_extra_info: callable = None
                     ):
        penalty = None
        if failed:
            penalty = self._failed_task()

        execution_cost = self._get_execution_cost(worker_class, is_internal=is_internal)
        waiting_cost = self._get_waiting_cost(task_class)
        if waiting_time < 0:
            waiting_time = 0
        self._log_reward_parameters(execution_time, execution_cost, waiting_cost, waiting_time)
        self._push_trajectory_extra_info(task_id,
                                         worker_class,
                                         waiting_time,
                                         waiting_cost,
                                         execution_cost,
                                         execution_time,
                                         push_trajectory_extra_info)

        return execution_cost, waiting_cost, waiting_time, penalty

    def compute(
            self,
            task_id: str,
            task_class: str,
            worker_class: str,
            waiting_time: float,
            execution_time: float,
            failed: bool,
            is_internal=True,
            push_trajectory_extra_info: callable = None,
            *args,
            **kwargs
    ) -> float:
        raise NotImplementedError('Compute method not implemented')

    def post_state_created(self, task_id: str, *args, **kwargs):
        pass

    def reset_internal_state(self, *args, **kwargs):
        pass


class WaitingTime(BaseRewardFunction):

    def __init__(
            self,
            global_config: GlobalConfigHelper,
            run_config: RunConfigHelper,
            execution_cost_calculator: ExecutionCostCalculator,
            logger: Logger,
            **kwargs
    ):
        super(WaitingTime, self).__init__(global_config, run_config, execution_cost_calculator, logger,
                                          name='WaitingTime')

    def compute(
            self,
            task_id: str,
            task_class: str,
            worker_class: str,
            waiting_time: float,
            execution_time: float,
            failed: bool,
            is_internal=True,
            push_trajectory_extra_info: callable = None,
            *args,
            **kwargs
    ) -> float:
        execution_cost, waiting_cost, waiting_time, penalty = self._pre_compute(
            task_id,
            task_class,
            worker_class,
            waiting_time,
            execution_time,
            failed,
            is_internal,
            push_trajectory_extra_info
        )
        if failed:
            return - (abs(float(penalty)))

        return float(- waiting_time)


class ExecutionTime(BaseRewardFunction):

    def __init__(
            self,
            global_config: GlobalConfigHelper,
            run_config: RunConfigHelper,
            execution_cost_calculator: ExecutionCostCalculator,
            logger: Logger,
            **kwargs
    ):
        super(ExecutionTime, self).__init__(global_config, run_config, execution_cost_calculator, logger,
                                            name='ExecutionTime')

    def compute(
            self,
            task_id: str,
            task_class: str,
            worker_class: str,
            waiting_time: float,
            execution_time: float,
            failed: bool,
            is_internal=True,
            push_trajectory_extra_info: callable = None,
            *args,
            **kwargs
    ) -> float:
        execution_cost, waiting_cost, waiting_time, penalty = self._pre_compute(
            task_id,
            task_class,
            worker_class,
            waiting_time,
            execution_time,
            failed,
            is_internal,
            push_trajectory_extra_info
        )
        if failed:
            return - (abs(float(penalty)))

        return float(- execution_time)


class ExecutionCost(BaseRewardFunction):

    def __init__(
            self,
            global_config: GlobalConfigHelper,
            run_config: RunConfigHelper,
            execution_cost_calculator: ExecutionCostCalculator,
            logger: Logger,
            **kwargs
    ):
        super(ExecutionCost, self).__init__(global_config, run_config, execution_cost_calculator, logger,
                                            name='ExecutionCost')

    def compute(
            self,
            task_id: str,
            task_class: str,
            worker_class: str,
            waiting_time: float,
            execution_time: float,
            failed: bool,
            is_internal=True,
            push_trajectory_extra_info: callable = None,
            *args,
            **kwargs
    ) -> float:
        execution_cost, waiting_cost, waiting_time, penalty = self._pre_compute(
            task_id,
            task_class,
            worker_class,
            waiting_time,
            execution_time,
            failed,
            is_internal,
            push_trajectory_extra_info
        )
        if failed:
            return - (abs(float(penalty)))

        return float(- (execution_time * execution_cost))


FUNCTIONS = {
    'waiting-time': WaitingTime,
    'execution-time': ExecutionTime,
    'execution-cost': ExecutionCost,
}


def get_reward_function(
        global_config: GlobalConfigHelper,
        run_config: RunConfigHelper,
        execution_cost_calculator: ExecutionCostCalculator,
        logger: Logger,
        reward_type=None,
        extra_params=None
):
    if reward_type is None:
        function = FUNCTIONS[run_config.reward_function_type()]
    else:
        function = FUNCTIONS[reward_type]
    if extra_params is not None:
        extra_parameters = extra_params
    else:
        extra_parameters = run_config.reward_function_extra_parameters()
    if extra_parameters is None:
        extra_parameters = {}
    return function(global_config, run_config, execution_cost_calculator, logger, **extra_parameters)
