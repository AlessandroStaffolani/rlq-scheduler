from rlq_scheduler.agent.agents.base import BaseAgent
from rlq_scheduler.common.experience_replay.experience_replay import ExperienceReplay
from rlq_scheduler.common.state.state_builder import StateBuilder


class EPVMAgent(BaseAgent):

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
                 experience_replay: ExperienceReplay = None,
                 alpha=1.5,
                 ):
        super(EPVMAgent, self).__init__(action_space,
                                        name='E-PVM',
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
        self.need_state = True
        # internal props
        self._n_worker_classes = self.run_config.count_available_worker_classes()
        # parameters
        self.alpha = alpha

        self.logger.info(f'Initialized {self.name} Agent using alpha {self.alpha}', resource='Agent')

    def choose_action(self, task_class=None, state=None, state_builder: StateBuilder = None):
        # least_chosen_actions
        if state is None:
            raise AttributeError('State is None, impossible to sample any workers')

        min_cost = None
        action = None
        workers_utilization = state_builder.load_workers_utilization()
        self.logger.debug(f'Worker classes utilization: {workers_utilization}')
        for worker_class, utilization in workers_utilization.items():
            worker_class_capacity = self.run_config.worker_class_capacity(worker_class)
            cost = self.alpha ** (utilization / worker_class_capacity)
            self.logger.debug('w_c: {} | cost: {} | w_c_capacity: {} | w_c_utilization: {}'
                              .format(worker_class, cost, worker_class_capacity, utilization))
            if min_cost is None or min_cost > cost:
                min_cost = cost
                action = worker_class
        action_index = self.action_space.get_action_index(action)
        # increase of 1 all the actions and set to 0 the value for the one selected
        self.action_attempts[action_index] += 1
        self.single_run_action_attempts[action_index] += 1
        self.logger.debug('Action taken from the {} Agent at time step {} is: index={}, value={}'
                          .format(self.name, self.t, str(action_index), action), resource='Agent')
        # increment the time step
        self.t += 1
        return action, action_index, None, None

    def observe_delayed_action(self, action, reward, state=None, next_state=None, context=None):
        return super().observe_delayed_action(action, reward, state, next_state, context)

    def multiply_reward(self, reward):
        return super(EPVMAgent, self).multiply_reward(reward)

    def get_parameters(self):
        return {
            'name': self.name,
            'mode': 'train' if self.train else 'eval',
            'use_external': self.is_external_worker_enabled(),
            'reward_multiplier': self.reward_multiplier,
            'agent_seed': self.random_seed,
            'alpha': self.alpha
        }

    def parameters_to_string(self):
        return f'alpha={self.alpha}'

    def get_serializable_content(self):
        serializable_content = super().get_serializable_content()
        return serializable_content

    def full_name(self):
        return self.name

    def __str__(self):
        return '<Agent name={} alpha={} current_time_step={} action_space={}>' \
            .format(self.name, self.alpha, self.t, str(self.action_space))
