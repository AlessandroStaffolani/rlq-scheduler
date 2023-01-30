from copy import deepcopy

import numpy as np

from rlq_scheduler.agent.agents.base import BaseAgent
from rlq_scheduler.common.experience_replay.experience_replay import ExperienceReplay
from rlq_scheduler.common.state.state import Features
from rlq_scheduler.common.state.state_builder import StateBuilder

GLOBAL_FEATURES = [
    'task_class_type',
    'resource_usage',
    'task_frequency'
]


class LinUCBAgent(BaseAgent):
    """
    Contextual Bandit Agent implemented using LinUCB algorithm

    Context features are:
        - task_class_type: type of the task for which choose and action
        - action: current action
    """

    def __init__(self,
                 action_space,
                 external_workers_config=None,
                 delta=1,
                 global_config=None,
                 run_config=None,
                 random_seed=0,
                 save_model_config=None,
                 train=True,
                 model_to_load=None,
                 reward_multiplier=1,
                 reward_multiplier_limit=None,
                 logger=None,
                 experience_replay: ExperienceReplay = None
                 ):
        """
        Abstract Agent constructor
        Parameters
        ----------
        action_space: list()
            list of actions available
        external_workers_config: dict
            configuration dictionary for present in the case in which the feature external workers is enabled. In that
            case the dictionary will contain:
                - enabled: bool
                    that is true if task broker will use workers external to its pool if necessary
                - action_prefix: str
                    prefix that will be used as prefix for all the action (except wait) in the agent action space
        """
        super(LinUCBAgent, self).__init__(action_space=action_space,
                                          name='LinUCB',
                                          external_workers_config=external_workers_config,
                                          global_config=global_config,
                                          run_config=run_config,
                                          random_seed=random_seed,
                                          save_model_config=save_model_config,
                                          train=train,
                                          model_to_load=model_to_load,
                                          reward_multiplier=reward_multiplier,
                                          reward_multiplier_limit=reward_multiplier_limit,
                                          logger=logger,
                                          experience_replay=experience_replay
                                          )
        self.need_state = False
        self.__delta = delta
        self.context_features: Features = Features(
            global_config=self.global_config,
            run_config=self.run_config,
            worker_classes=self.run_config.available_worker_classes(),
            task_classes=self.run_config.available_tasks_classes(),
            features=self.run_config.context_features()
        )
        self.context_size = self.context_features.size()
        self.alpha = self._define_alpha(delta=self.__delta)
        self.A = self._initialize_A()
        self.b = np.zeros((self.action_space.size(), self.context_size, 1))
        self.confidence_interval = np.zeros((self.action_space.size(), self.context_size, 1))
        # init agent, depending on train and load_model config parameters
        self._load_model()

    def choose_action(self, task_class=None, state=None, state_builder: StateBuilder = None):
        # update the global features of the context
        self.update_global_context_features(task_class, state_builder)
        if self.run_config.is_bootstrapping_enabled() \
                and self.n_reward_observation < self.run_config.tasks_bootstrapping_tasks_to_generate():
            action, action_index, _, _ = self.bootstrap_action()
            context = self.compute_context(action_index, state_builder=state_builder)
            return action, action_index, context, None
        # check if any action is never been selected
        never_chosen_action = np.where(self.action_attempts == 0)[0]
        if len(never_chosen_action) > 0:
            # at least one is never been selected, return the first one
            action_index = never_chosen_action[0]
            action = self.action_space.get_action(action_index)
            context = self.compute_context(action_index, state_builder=state_builder)
            # update action attempt of the action selected
            self.action_attempts[action_index] += 1
            self.single_run_action_attempts[action_index] += 1
            self.logger.debug('Action taken from the {} Agent at time step {} is: index={}, value={}, context={}'
                              .format(self.name, self.t, str(action_index), action, str(context)), resource='Agent')
            # increment the time step
            self.t += 1
            return action, action_index, context, None
        else:
            # compute the confidence interval for each action
            actions_context = self.compute_confidence_intervals_and_contexts(state_builder=state_builder)
            # choose the action
            arg_max = np.argmax(self.confidence_interval)
            action_index = np.unravel_index(arg_max, self.confidence_interval.shape)[0]
            # return the action
            action = self.action_space.get_action(action_index)
            action_context = actions_context[action_index]
            # update action attempt of the action selected
            self.action_attempts[action_index] += 1
            self.single_run_action_attempts[action_index] += 1
            self.logger.debug('Action taken from the {} Agent at time step {} is: index={}, value={}, context={}'
                              .format(self.name, self.t, str(action_index), action, str(action_context)), resource='Agent')
            # increment the time step
            self.t += 1
            return action, action_index, action_context, None

    def observe_delayed_action(self, action, reward, state=None, next_state=None, context=None):
        if not self.train:
            self.update_reward(reward)
            return
        self.logger.debug('Agent is observing delayed reward with args: Action = {} | reward = {} | state = {} | '
                          'next_state = {} | context = {}'
                          .format(action, reward, state, next_state, context), resource='Agent')

        # update A
        self.A[action] += context @ np.transpose(context)
        # update b
        self.b[action] += reward * context
        # update counter and reward history
        self.n_reward_observation += 1
        self.update_reward(reward)
        self.logger.debug('After having observed reward A[a] = {} and b[a] = {}'.format(self.A[action], self.b[action]), resource='Agent')
        return

    def compute_confidence_intervals_and_contexts(self, state_builder):
        actions_context = []
        for i, _ in enumerate(self.action_space):
            context = self.compute_context(i, state_builder=state_builder)
            actions_context.append(context)
            A_t_reversed = np.linalg.inv(self.A[i])
            # operator @ allow to obtain from a (n x n) * (n x 1) a (n x 1) matrix, otherwise you get a (n x n)
            theta = A_t_reversed @ self.b[i]
            # split the confidence_interval operation in 2 side (left and right) and then I sum them
            left = np.transpose(theta) @ context
            right = np.sqrt(np.transpose(context) @ A_t_reversed @ context)
            self.confidence_interval[i] = left + self.alpha * right
        return actions_context

    def update_global_context_features(self, task_class, state_builder):
        if task_class is None or state_builder is None:
            raise AttributeError('update global context features failed, task_class and state_builder can not be None')
        state_builder.update_global_features(task_class=task_class, features=self.context_features)

    def compute_context(self, action_index, state_builder: StateBuilder):
        """
        Compute the context based on the value of task and the action
        Parameters
        ----------
        action_index: int
            action index of the action for which compute the current context
        state_builder: StateBuilder
            state builder instance
        Returns
        -------
        State
            state generate from the state_properties
        """
        if state_builder is None:
            raise AttributeError('compute context failed, state_builder can not be None')
        state_builder.update_non_global_features(action_index=action_index, features=self.context_features)
        context = self.context_features.to_state()
        self.logger.debug('Current context = {}'.format(str(context)), resource='Agent')
        return context

    def get_parameters(self):
        return {
            'name': self.name,
            'mode': 'train' if self.train else 'eval',
            'delta': self.__delta,
            'context_size': self.context_size,
            'use_external': self.is_external_worker_enabled(),
            'reward_multiplier': self.reward_multiplier,
            'agent_seed': self.random_seed
        }

    def update_context_global_features(self):
        """
        Update the context features which are the same for each action context, like task_class_type or resource_usage
        :return:
        """
        pass

    def log_status(self):
        self.logger.debug('Agent total_reward = {}'.format(str(np.round(self.total_reward, 4))), resource='Agent')

    def _initialize_A(self):
        """
        Initialize matrix A of the LinUCB algorithm to be of dimension (Action_space_size x context_sixe x context_size)
        and having the context_size identity matrix for each action
        Returns
        -------
        numpy.ma.core.MaskedArray
            the initialized A matrix
        """
        A = np.zeros((self.action_space.size(), self.context_size, self.context_size))
        for i, _ in enumerate(A):
            A[i] = np.identity(self.context_size)
        return A

    def minimal_info(self):
        return '<Agent name={} delta={} context_size={}>'.format(self.name, str(self.__delta), str(self.context_size))

    def full_name(self):
        return self.name

    def to_filename_string(self):
        return self.name + '__delta={}__ctx_size={}'.format(str(self.__delta), str(self.context_size))

    def parameters_to_string(self):
        return 'delta={}_ctx_size={}'\
            .format(str(self.__delta), str(self.context_size))

    def __str__(self):
        return '<Agent name={} mode={} context_size={} action_space={}>' \
            .format(self.name, 'train' if self.train else 'evaluate', str(self.context_size), str(self.action_space))

    def get_serializable_content(self):
        serializable_content = super().get_serializable_content()
        serializable_content['A'] = self.A
        serializable_content['b'] = self.b
        serializable_content['confidence_interval'] = self.confidence_interval
        return serializable_content

    def _agent_specific_load_model(self):
        if self.model_to_load is not None:
            self.A = deepcopy(np.array(self.model_to_load['A']))
            self.b = deepcopy(np.array(self.model_to_load['b']))
            self.confidence_interval = deepcopy(np.array(self.model_to_load['confidence_interval']))

    @staticmethod
    def _define_alpha(delta):
        """
        Define the parameter alpha of the LinUCB algorithm
        Parameters
        ----------
        delta

        Returns
        -------
        float
         the computed alpha value
        """
        return 1 + np.sqrt(np.log(2 / delta) / 2)
