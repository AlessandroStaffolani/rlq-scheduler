from copy import deepcopy

import numpy as np

from rlq_scheduler.agent.agents.action_space import ActionSpace
from rlq_scheduler.common.config_helper import GlobalConfigHelper, RunConfigHelper
from rlq_scheduler.common.experience_replay.experience_replay import ExperienceReplay
from rlq_scheduler.common.state.state_builder import StateBuilder
from rlq_scheduler.common.stats import StatsBackend
from rlq_scheduler.common.utils.logger import get_logger

LOGGER_CONFIG = {
    'name': 'agent',
    'level': 10,
    'handlers': [
        {'type': 'console', 'parameters': None}
    ]
}


class BaseAgent:
    """
    Base Agent class which implements a random agent
    Attributes
    ----------
    action_space: list()
        list of available actions type
    """

    def __init__(self,
                 action_space,
                 name='',
                 external_workers_config=None,
                 global_config: GlobalConfigHelper = None,
                 run_config: RunConfigHelper = None,
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
        name: str
            name of the agent
        external_workers_config: dict | None
            configuration dictionary for present in the case in which the feature external workers is enabled. In that
            case the dictionary will contain:
                - enabled: bool
                    that is true if task broker will use workers external to its pool if necessary
                - action_prefix: str
                    prefix that will be used as prefix for all the action (except wait) in the agent action space
        global_config: dict | None
            dictionary with the configuration of the environment
        random_seed: int
            seed used by the random generator used by the Agent
        save_model_config: dict | None
            configuration dictionary with the info for saving the Agent model
        train: bool
            flag for setting the Agent in train or evaluation mode, default True
        model_to_load: Model | None
            agent model deserialized to load or None
        reward_multiplier: int
            value multiplied to the reward, default 1
        """
        # protected properties
        self._external_workers_config = external_workers_config
        # public properties
        self.need_state = False
        self.logger = logger if logger is not None else get_logger(LOGGER_CONFIG)
        self.global_config: GlobalConfigHelper = global_config
        self.run_config: RunConfigHelper = run_config
        self.action_space = ActionSpace(actions=action_space, external_workers_config=self._external_workers_config)
        self.name = name
        self.total_reward = 0
        self.reward_multiplier = reward_multiplier
        self.reward_multiplier_limit = reward_multiplier_limit
        self.reward_history = [self.total_reward]
        # in this environment an episode correspond to the validation_test_frequency property of the configuration
        self.cumulative_reward_over_validation_window = 0
        self.avg_cumulative_reward_over_validation_window = []
        self.action_attempts = np.zeros(self.action_space.size())
        self.single_run_action_attempts = np.zeros(self.action_space.size())
        self.t = 0
        self.random_seed = random_seed
        self.random = np.random.RandomState(self.random_seed)
        self.logger.info('Set random seed for the agent to: {}'.format(self.random_seed))
        # count how many time the observe_delayed_action method is called
        self.n_reward_observation = 0
        self.losses = []
        self.save_model_config = save_model_config
        self.train = train
        self.model_to_load = model_to_load
        self.validation_reward_history = []
        self.run_code = None
        self.experience_replay: ExperienceReplay = experience_replay
        self.stats_backend: StatsBackend = StatsBackend(global_config=self.global_config, logger=self.logger)

    def reset(self):
        """
        Reset the agent
        """
        self.total_reward = 0
        self.reward_history = [self.total_reward]

    def get_action_space(self):
        """
        Return the action space as list()
        Returns
        -------
        list()
            the action space list
        """
        return self.action_space.get_actions()

    def random_choice(self):
        return self.random.randint(0, self.action_space.size())

    def bootstrap_action(self):
        action_index = self.random_choice()
        action = self.action_space.get_action(action_index)
        self.action_attempts[action_index] += 1
        self.single_run_action_attempts[action_index] += 1
        self.logger.debug(f'Bootstrapping action {self.t} selecting action {action} with index {action_index}')
        self.t += 1
        return action, action_index, None, None

    def choose_action(self, task_class=None, state=None, state_builder: StateBuilder = None):
        """
        Choose action take a task and using the information from the
        state choose the best action (the worker_class) to return as action to the TaskBroker
        Parameters
        ----------
        task_class: Task | None
            task for which choose an action
        state: State | None
            current state
        state_builder: StateBuilder | None
            state builder instance
        Returns
        -------
        tuple
            where the first item is the action value, the second is the action index on the action space, the third
            value is the context used for computing the action (if available, otherwise is None) and the fourth element
             is the epsilon used (available only on DQN with epsilon decay)
        """
        if self.run_config.is_bootstrapping_enabled() \
                and self.n_reward_observation < self.run_config.tasks_bootstrapping_tasks_to_generate():
            return self.bootstrap_action()
        self.logger.debug('Agent at time step {} is going to choose action with task={}, state={}'
                          .format(self.t, task_class, np.reshape(state, (-1,))), resource='Agent')
        # chose a random index from the unmasked action indexes
        action_index = self.random_choice()
        action = self.action_space.get_action(action_index)
        self.action_attempts[action_index] += 1
        self.single_run_action_attempts[action_index] += 1
        self.logger.info(f'Agent choose action {action} with index {action_index}', resource='Agent')
        # increment the time step
        self.t += 1
        return action, action_index, None, None

    def observe_delayed_action(self, action, reward, state=None, next_state=None, context=None):
        """
        Observe the reward of the action executed some time step ago
        Parameters
        ----------
        action: int
            action executed (the action index)
        reward: float
            reward obtained to be updated in the table
        state: State | None
            state used to perform the action that cause the update or state resulting to the update
        next_state: State | None
            state used to perform the action that cause the update or state resulting to the update
        context:
            context used by contextual bandit to choose the action
        Returns
        -------
        None | float
            Return None or the loss of the gradient in the DQN agents
        """
        self.logger.debug('Agent observe delayed reward args: Action = {} | reward = {} | state = {} | '
                          'next_state = {} | context = {}'
                          .format(action, reward, state, next_state, context), resource='Agent')
        self.n_reward_observation += 1
        self.update_reward(reward)
        return

    def get_parameters(self):
        """
        Get the parameters of the Agent
        Returns
        -------
        dict
            with the parameters of the agent
        """
        return {
            'name': self.name,
            'mode': 'train' if self.train else 'eval',
            'use_external': self.is_external_worker_enabled(),
            'reward_multiplier': self.reward_multiplier,
            'agent_seed': self.random_seed
        }

    def multiply_reward(self, reward):
        value = reward * self.reward_multiplier
        if self.reward_multiplier_limit is not None:
            return min(value, self.reward_multiplier_limit)
        else:
            return value

    def update_reward(self, reward):
        """
        Update the reward its an independent method because we need to update it also in time step in which we don't
        any task end
        Parameters
        ----------
        reward: float
            reward value
        """
        self.total_reward += reward
        self.reward_history.append(self.total_reward)
        if self.run_code is not None:
            self.stats_backend.save_stats_group_property(
                stats_run_code=self.run_code,
                prop='reward',
                value=reward,
                as_list=True
            )
            # update the cumulative reward of the episode
            # self.cumulative_reward_over_validation_window += reward
            # if self.n_reward_observation % self.run_config.validation_test_frequency() == 0:
            #     #
            #     n_avg = self.n_reward_observation // self.run_config.validation_test_frequency()
            #     avg_cum_reward = self.cumulative_reward_over_validation_window / n_avg
            #     self.avg_cumulative_reward_over_validation_window.append(avg_cum_reward)
            #     self.cumulative_reward_over_validation_window = 0
            #     self.stats_backend.save_stats_group_property(
            #         stats_run_code=self.run_code,
            #         prop='avg_validation_cumulative_reward',
            #         value=avg_cum_reward,
            #         as_list=True
            #     )
            #     self.logger.info('Saved average cumulative reward for time window {} with average {}'
            #                      .format(n_avg, avg_cum_reward), resource='Agent')

    def push_experience_entry(self, state, action, reward, next_state):
        pass

    def observe_offline_experience(self, no_debug=False):
        pass

    def is_external_worker_enabled(self):
        """
        Return True if the external worker feature is enabled, False otherwise
        Returns
        -------
        bool
        """
        if self._external_workers_config is None or self._external_workers_config['enabled'] is False:
            return False
        else:
            return True

    def get_external_worker_prefix(self):
        """
        if the external worker feature is enabled, return the prefix used in the actions, otherwise return None
        Returns
        -------
        str | None
        """
        if self._external_workers_config is None and self._external_workers_config['enabled'] is False:
            return None
        else:
            return self._external_workers_config['action_prefix']

    def log_status(self):
        """
        Show in the log the status of the agent (total_reward and other information)
        """
        self.logger.debug('Agent total_reward = {}'.format(str(np.round(self.total_reward, 4))), resource='Agent')

    def minimal_info(self):
        return '<Agent name={}>'.format(self.name)

    def full_name(self):
        return self.name

    def to_filename_string(self):
        return self.name

    def parameters_to_string(self):
        """
        Returns the string representation of the parameters of the agent
        Returns
        -------
        str
        """
        pass

    def is_save_model_enabled(self):
        if self.save_model_config is not None and 'enabled' in self.save_model_config and \
                self.save_model_config['enabled'] is True:
            return True
        else:
            return False

    def get_serializable_content(self):
        # I'm not using agent.t because when I restart
        # I want to execute the tasks for which I've not obtained the reward yet
        return {
            'name': self.name,
            'full_name': self.full_name(),
            'total_reward': self.total_reward,
            'reward_history': self.reward_history,
            'action_attempts': self.action_attempts,
            't': self.n_reward_observation,
            'random': self.random,
            'random_seed': self.random_seed,
            'n_reward_observation': self.n_reward_observation
        }

    def __str__(self):
        return '<Agent name={} mode={} current_time_step={} action_space={}>' \
            .format(self.name, 'train' if self.train else 'eval', self.t, str(self.action_space))

    def _load_model(self):
        """
        Take a valid path and load the model from the filesystem
        """
        if self.model_to_load is not None:
            self.total_reward = deepcopy(self.model_to_load['total_reward'])
            self.reward_history = deepcopy(self.model_to_load['reward_history'])
            self.action_attempts = deepcopy(np.array(self.model_to_load['action_attempts']))
            self.t = deepcopy(self.model_to_load['t'])
            self.random = deepcopy(self.model_to_load['random'])
            self.random_seed = deepcopy(self.model_to_load['random_seed'])
            self.n_reward_observation = deepcopy(self.model_to_load['n_reward_observation'])
            self._agent_specific_load_model()
            del self.model_to_load
            self.model_to_load = None
            self.logger.info('Loaded agent model', resource='Agent')

    def _agent_specific_load_model(self):
        pass

    @staticmethod
    def get_n_reward_observation_from_filename(filename_path):
        """
        Get the n_reward_observation value from a filename (full path plus filename)
        Parameters
        ----------
        filename_path: str
            filename plus path
        Returns
        -------
        int
            the value
        """
        # last item of the split is the filename, then remove extension '.pht'
        filename_no_ext = filename_path.split('/')[-1][0:-4]
        n_reward_observation_field = filename_no_ext.split('__')[-1]
        return int(n_reward_observation_field.split('=')[-1])
