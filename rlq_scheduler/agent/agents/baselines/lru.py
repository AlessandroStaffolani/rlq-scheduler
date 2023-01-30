import numpy as np

from rlq_scheduler.agent.agents.base import BaseAgent
from rlq_scheduler.common.experience_replay.experience_replay import ExperienceReplay
from rlq_scheduler.common.state.state_builder import StateBuilder


class LRUAgent(BaseAgent):

    def __init__(self,
                 action_space,
                 external_workers_config=None,
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
        super(LRUAgent, self).__init__(action_space,
                                       name='LRU',
                                       external_workers_config=external_workers_config,
                                       global_config=global_config,
                                       run_config=run_config,
                                       random_seed=random_seed,
                                       save_model_config=save_model_config,
                                       train=True,
                                       model_to_load=model_to_load,
                                       reward_multiplier=reward_multiplier,
                                       reward_multiplier_limit=reward_multiplier_limit,
                                       logger=logger,
                                       experience_replay=experience_replay
                                       )
        self.unused_actions_table = np.zeros(self.action_space.size())
        self.need_state = False

    def choose_action(self, task_class=None, state=None, state_builder: StateBuilder = None):
        self.logger.debug('Agent at time step {} is going to choose action unused_table: {}'
                          .format(self.t, self.unused_actions_table), resource='Agent')
        # least_chosen_actions
        least_chosen_actions = np.argwhere(self.unused_actions_table == np.amax(self.unused_actions_table)).squeeze(-1)
        # get a random index from least_chosen_actions
        least_chose_index = self.random.choice(len(least_chosen_actions))
        action_index = least_chosen_actions[least_chose_index]
        # get the action name of the action selected
        action = self.action_space.get_action(action_index)
        # increase of 1 all the actions and set to 0 the value for the one selected
        self.unused_actions_table += 1
        self.unused_actions_table[action_index] = 0
        self.action_attempts[action_index] += 1
        self.single_run_action_attempts[action_index] += 1
        self.logger.info(f'Agent choose action {action} with index {action_index}', resource='Agent')
        # increment the time step
        self.t += 1
        return action, action_index, None, None

    def observe_delayed_action(self, action, reward, state=None, next_state=None, context=None):
        return super().observe_delayed_action(action, reward, state, next_state, context)

    def multiply_reward(self, reward):
        return reward

    def get_parameters(self):
        return {
            'name': self.name,
            'mode': 'train' if self.train else 'eval',
            'use_external': self.is_external_worker_enabled(),
            'reward_multiplier': self.reward_multiplier,
            'agent_seed': self.random_seed
        }

    def parameters_to_string(self):
        return ''

    def get_serializable_content(self):
        serializable_content = super().get_serializable_content()
        return serializable_content

    def full_name(self):
        return self.name

    def __str__(self):
        return '<Agent name={} current_time_step={} action_space={}>' \
            .format(self.name, self.t, str(self.action_space))
