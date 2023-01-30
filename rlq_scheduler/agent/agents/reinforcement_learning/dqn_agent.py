import torch
import torch.nn.functional as F
import torch.optim as optim
import numpy as np

from rlq_scheduler.agent.agents.base import BaseAgent
from rlq_scheduler.agent.agents.epsilon_parameter import get_epsilon, EpsilonScalar,\
    EpsilonExponentialDecay
from rlq_scheduler.common.experience_replay.experience_replay import ExperienceReplay, ExperienceEntry
from rlq_scheduler.agent.agents.reinforcement_learning.q_network import QNetworkFactory
from rlq_scheduler.common.config_helper import GlobalConfigHelper
from rlq_scheduler.common.state.state import state_to_tensor
from rlq_scheduler.common.state.state_builder import StateBuilder


class DQNAgent(BaseAgent):
    """
    Deep Q-learning Agent with experience replay
    Attributes
    ----------
    epsilon: EpsilonScalar | EpsilonExponentialDecay
    experience_replay_capacity: ExperienceReplay
    """

    def __init__(self,
                 action_space,
                 network_config,
                 experience_replay_capacity=2000,
                 learning_rate=0.0001,
                 gamma=0.99,
                 batch_size=128,
                 target_net_update_frequency=100,
                 epsilon='scalar',
                 optimizer='adam',
                 external_workers_config=None,
                 global_config=None,
                 run_config=None,
                 random_seed=0,
                 save_model_config=None,
                 train=True,
                 model_to_load=None,
                 name='DQN',
                 reward_multiplier=1,
                 reward_multiplier_limit=None,
                 logger=None,
                 experience_replay: ExperienceReplay = None
                 ):
        """
        Constructor
        Parameters
        ----------
        action_space: list
        network_config: dict
        experience_replay_capacity: int
        learning_rate: float
        gamma: float
        batch_size: int
        target_net_update_frequency: int
        epsilon: str | dict
        optimizer: str
        external_workers_config: dict
        global_config: GlobalConfigHelper
        random_seed: int
        save_model_config: dict
        train: bool
        load_model_config: dict
        name: str
        """
        super(DQNAgent, self).__init__(action_space,
                                       name=name,
                                       external_workers_config=external_workers_config,
                                       global_config=global_config,
                                       run_config=run_config,
                                       random_seed=random_seed,
                                       save_model_config=save_model_config,
                                       train=train,
                                       model_to_load=model_to_load,
                                       reward_multiplier=reward_multiplier,
                                       reward_multiplier_limit=reward_multiplier_limit,
                                       logger=logger)
        self.need_state = True
        # set the random seed also for torch
        torch.manual_seed(self.random_seed)
        self.logger.info('Set random seed for torch to: {}'.format(self.random_seed), resource='Agent')
        # store all the parameters as protected variables
        self._learning_rate = learning_rate
        self._gamma = gamma
        self._batch_size = batch_size
        self._target_network_update_frequency = target_net_update_frequency
        if isinstance(epsilon, str):
            self._epsilon = get_epsilon(epsilon)
        else:
            self._epsilon = get_epsilon(epsilon['type'], **epsilon['parameters'])
        self.logger.info('Agent {} epsilon is {}'.format(self.full_name(), self._epsilon), resource='Agent')
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        # get the size of state
        self.state_size = self.run_config.state_size()
        net_name, net_arguments = self._prepare_net_config(network_config)
        self.network_type = net_name
        if 'hidden_layers' in net_arguments:
            self.network_layers = net_arguments['hidden_layers']
        else:
            self.network_layers = None
        # create the action-value network = Q(theta)
        self.action_value_network = QNetworkFactory.get_net(self.network_type, **net_arguments)
        # create the target network = Q(theta^)
        self.target_network = QNetworkFactory.get_net(self.network_type, **net_arguments)
        # copy the weights of action-value network on the target network
        self._copy_network_weights()
        # define the experience replay
        if experience_replay is None:
            self.experience_replay = ExperienceReplay(capacity=experience_replay_capacity)
        else:
            self.experience_replay = experience_replay
        # initialize the optimizer
        self.optimizer = DQNAgent.get_optimizer(optimizer, network=self.action_value_network, lr=self._learning_rate)
        # validation info
        # self.best_validation_reward = 0
        # self.patience = 0
        # self.patience_current_level = 0
        # self.validation_enabled = False
        # self._init_validation_info()
        # init agent, depending on train and load_model config parameters
        self._load_model()

    def choose_action(self, task_class=None, state=None, state_builder: StateBuilder = None):
        if self.run_config.is_bootstrapping_enabled() \
                and self.n_reward_observation < self.run_config.tasks_bootstrapping_tasks_to_generate():
            return self.bootstrap_action()
        self.logger.debug('at time step = {} agent is going to use state {} for action selection'
                          .format(self.t, list(state)), resource='Agent')
        # make the state a tensor
        state = state_to_tensor(state, device=self._device).view(-1, state.size)
        epsilon = self._epsilon.value(self.t)
        self.logger.debug('At time {} epsilon used to choose the action is {}'.format(self.t, epsilon), resource='Agent')
        if self.random.random() < epsilon and self.train:
            # chose a random index from the actions
            action_index = self.random.randint(0, self.action_space.size())
        else:
            with torch.no_grad():
                # use the action-value function to get the probabilities for all the actions
                action_probabilities = self.action_value_network(state)
                self.logger.debug('Agent {} actions probabilities are = {}'.format(self.name, action_probabilities), resource='Agent')
                # get the max probability the action as action_index selected
                action_index = action_probabilities.max(1)[1]
                action_index = action_index.item()

        # use the action index to return also the action name
        action = self.action_space.get_action(action_index)
        self.action_attempts[action_index] += 1
        self.single_run_action_attempts[action_index] += 1
        self.logger.debug('Action taken from the {} Agent at time step {} is: index={}, value={}, epsilon={}'
                          .format(self.name, self.t, str(action_index), action, self._epsilon.epsilon), resource='Agent')
        # increment the time step
        self.t += 1
        return action, action_index, None, epsilon

    def observe_delayed_action(self, action, reward, state=None, next_state=None, context=None):
        # update counter and reward history
        if self.train:
            return self.optimize_model(reward)
        else:
            # if I'm in the case in which I'm not training I don't need to optimize the model
            self.update_reward(reward)
            return

    def optimize_model(self, reward):
        if len(self.experience_replay) < self._batch_size:
            # if no sufficient experience in the experience replay the agent should act random
            # and not updating the networks weights
            self.losses.append(0)
            self.n_reward_observation += 1
            self.update_reward(reward)
            self._add_loss_to_stats(0)
            return
        # sample from the experience and perform an optimization step
        loss = self._optimize_step()

        self._update_target_network(loss)

        # add the loss already computed
        self.losses.append(loss)
        # update counter
        self.n_reward_observation += 1
        self.update_reward(reward)
        self._add_loss_to_stats(loss)
        return loss

    def _optimize_step(self):
        # sample the experience replay each entry is a ExperienceEntry with: state, action, reward, next_state
        samples = self.experience_replay.sample(self._batch_size)
        # transform the array of ExperienceEntry in a ExperienceEntry where each elements is a list,
        # so we have as first element we have the list of all state, all actions, all rewards and all the next states
        batch = ExperienceEntry(*zip(*samples))
        # get the batch for each element
        batch_states = torch.cat(batch.state)
        batch_actions = torch.cat(batch.action)
        batch_rewards = torch.cat(batch.reward)
        batch_next_states = torch.cat(batch.next_state)

        expected_state_action_values = self._compute_expected_state_action_values(batch_next_states, batch_rewards)

        # take from the action_value function the state_action_value "Q(s, a, theta)". net.gather(1, batch_actions)
        # on index 1 (for every row) take the value corresponding to the action.
        # Essentially I'm taking for each action i, the state from which I've taken the action
        state_action_values = self.action_value_network(batch_states)
        state_action_values = state_action_values.gather(1, batch_actions)

        # calculating the loss between the target and the state action values -> (Y-Q(s,a,theta))^2
        # should be a difference squared, but to avoid super big values that can stuck the network into
        # a local min/max we smooth the value up to certain value computing Huber loss
        loss = F.smooth_l1_loss(input=state_action_values, target=expected_state_action_values)

        # perform the operations necessary to compute a backward optimization step
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        return loss.item()

    def _update_target_network(self, loss, no_debug=False):
        # check if target_network_update_frequency time steps have been done to eventually copy
        # the weights from the action-value network to the target network
        if self.n_reward_observation % self._target_network_update_frequency == 0:
            self._copy_network_weights()
            self.logger.info('Target network\'s weights have been updated using those of the action-value function',
                             resource='Agent')
        if no_debug is False:
            self.logger.debug('Optimization step number {} - current loss = {}'
                              .format(self.n_reward_observation, self.name, str(loss)), resource='Agent')

    def observe_offline_experience(self, no_debug=False):
        loss = self._optimize_step()
        self._update_target_network(loss, no_debug)
        # add the loss already computed
        self.losses.append(loss)
        self.n_reward_observation += 1
        self.t += 1
        return loss

    def _add_loss_to_stats(self, loss):
        if self.run_code is not None:
            self.stats_backend.save_stats_group_property(
                stats_run_code=self.run_code,
                prop='loss',
                value=loss,
                as_list=True
            )
            self.logger.debug('Added current loss value to stats', resource='Agent')

    def _compute_expected_state_action_values(self, batch_next_states, batch_rewards):
        """
        Compute the target `expected_state_action_values` that will be used for computing the update of
        action-value network. This is done separately to allow easy extension of the class for implementing
        the Double-DQN algorithm
        Parameters
        ----------
        batch_next_states: torch.tensor
            tensor with the next_states sampled from the experience replay
        batch_rewards: torch.tensor
            tensor with the rewards sampled from the experience replay
        Returns
        -------
        torch.tensor
            returns
        """
        # using the target policy get the next state values "max_a'Q(s_t+1, a', theta^)". theta^ = target policy,
        # a' is the value by which we have max value in the Q
        next_state_values = self.target_network(batch_next_states)

        # max returns a tuple where the first item is the max value, while the second element is the index of the max
        next_state_values = next_state_values.max(dim=1)[0]

        # compute the expected state action values used as target for computing the loss "y"
        # max of next is not necessary, it has been done in the computation of next_state_values
        expected_state_action_values = (next_state_values * self._gamma) + batch_rewards
        # the results is unsqueeze to match the size of the state_action_values
        return expected_state_action_values.unsqueeze(1)

    def get_parameters(self):
        return {
            'name': self.name,
            'mode': 'train' if self.train else 'eval',
            'state_size': self.state_size,
            'action_space_size': self.action_space.size(),
            'network': self.network_type,
            'network_layers': self.network_layers,
            'learning_rate': self._learning_rate,
            'gamma': self._gamma,
            'batch_size': self._batch_size,
            'target_network_update_frequency': self._target_network_update_frequency,
            'epsilon': str(self._epsilon),
            'reward_multiplier': self.reward_multiplier,
            'agent_seed': self.random_seed
        }

    def push_experience_entry(self, state, action, reward, next_state):
        """
        Add a new entry in the experience replay
        Parameters
        ----------
        state: State
            State object in which the action `action` has been taken
        action: int
            action taken by the agent at state `state`
        reward: float
            reward observed applying action `action` to state `state`
        next_state: State
            State object in which goes the environment after applying action `action`
        """
        tensor_state = state_to_tensor(state, device=self._device)
        tensor_next_state = state_to_tensor(next_state, device=self._device)
        # state.view(-1, state.size) necessary to transform the size of the State from (size, 1), to (size,)
        self.experience_replay.push(
            tensor_state.view(-1, state.size),
            torch.tensor([[action]], device=self._device, dtype=torch.long),
            torch.tensor([reward], device=self._device, dtype=torch.float),
            tensor_next_state.view(-1, next_state.size)
        )
        self.logger.debug('New entry added to the experience replay. ExperienceReplay = {}'
                          .format(str(self.experience_replay)), resource='Agent')

    def log_status(self):
        self.logger.debug('Agent total_reward = {}'.format(str(np.round(self.total_reward, 4))), resource='Agent')

    def minimal_info(self):
        return '<Agent name={} network={} learning_rate={} gamma={} batch_size={} ' \
               'epsilon={} target_network_update_frequency={}>' \
            .format(self.name, self.network_type, str(self._learning_rate), str(self._gamma),
                    str(self._batch_size), str(self._epsilon), str(self._target_network_update_frequency))

    def full_name(self):
        return self.name

    def to_filename_string(self):
        return self.name + '__network={}__learning_rate={}__gamma={}__batch_size={}__epsilon={}' \
            .format(self.network_type, str(self._learning_rate), str(self._gamma), str(self._batch_size),
                    str(self._epsilon))

    def parameters_to_string(self):
        return 'network={}_layers={}_lr={}_batch_size={}_epsilon={}_gamma={}'\
            .format(self.network_type,
                    str(self.network_layers),
                    str(self._learning_rate),
                    str(self._batch_size),
                    str(self._epsilon),
                    str(self._gamma)
                    )

    def __str__(self):
        return '<Agent name={} mode={} learning_rate={} gamma={} batch_size={} epsilon={}' \
               ' target_network_update_frequency={} action_space={}>' \
            .format(self.name, 'train' if self.train else 'eval', str(self._learning_rate), str(self._gamma),
                    str(self._batch_size), str(self._epsilon), str(self._target_network_update_frequency),
                    str(self.action_space))

    def _prepare_net_config(self, network_config):
        name = network_config['type']
        arguments = {
            'input_size': self.state_size,
            'output_size': self.action_space.size()
        }
        if 'parameters' in network_config and network_config['parameters'] is not None:
            for key, value in network_config['parameters'].items():
                arguments[key] = value
        return name, arguments

    def _copy_network_weights(self):
        """
        Copy the weights of the action-value function network into the target network
        """
        self.target_network.load_state_dict(self.action_value_network.state_dict())
        self.target_network.eval()

    def get_serializable_content(self):
        serializable_content = super().get_serializable_content()
        serializable_content['model_state_dict'] = self.action_value_network.state_dict()
        serializable_content['optimizer_state_dict'] = self.optimizer.state_dict()
        serializable_content['losses'] = self.losses
        return serializable_content

    def _agent_specific_load_model(self):
        if self.model_to_load is not None:
            self.action_value_network.load_state_dict(self.model_to_load['model_state_dict'])
            self.optimizer.load_state_dict(self.model_to_load['optimizer_state_dict'])
            self._copy_network_weights()
            self.losses = self.model_to_load['losses']

    @staticmethod
    def get_optimizer(optimizer_name, network, **kwargs):
        """
        From the name of the optimizer and return the optimizer. If optimizer name is not correct it will use Adam
        optimizer as default one
        Parameters
        ----------
        optimizer_name: str
            name of the optimizer
        network: torch.nn.Module
            network from which take the parameters used by the optimizer
        Returns
        -------
        torch.optim.Adam
            optimizer
        """
        switcher = {
            'adam': optim.Adam(params=network.parameters(), **kwargs)
        }
        if optimizer_name in switcher:
            return switcher[optimizer_name]
        else:
            return optim.Adam(params=network.parameters(), **kwargs)


class DoubleDQNAgent(DQNAgent):
    """
    Double DQN agent which extends the DQNAgent changing only how it computes the
    expected_state_action_values (target Y)
    """

    def __init__(self,
                 action_space,
                 network_config,
                 experience_replay_capacity=2000,
                 learning_rate=0.0001,
                 gamma=0.99,
                 batch_size=128,
                 target_net_update_frequency=100,
                 epsilon='scalar',
                 optimizer='adam',
                 external_workers_config=None,
                 global_config=None,
                 run_config=None,
                 random_seed=0,
                 save_model_config=None,
                 train=True,
                 model_to_load=None,
                 name='DoubleDQN',
                 reward_multiplier=1,
                 reward_multiplier_limit=None,
                 logger=None,
                 experience_replay: ExperienceReplay = None
                 ):
        super(DoubleDQNAgent, self).__init__(action_space,
                                             network_config,
                                             experience_replay_capacity=experience_replay_capacity,
                                             learning_rate=learning_rate,
                                             gamma=gamma,
                                             batch_size=batch_size,
                                             target_net_update_frequency=target_net_update_frequency,
                                             epsilon=epsilon,
                                             optimizer=optimizer,
                                             external_workers_config=external_workers_config,
                                             global_config=global_config,
                                             run_config=run_config,
                                             random_seed=random_seed,
                                             save_model_config=save_model_config,
                                             train=train,
                                             model_to_load=model_to_load,
                                             name=name,
                                             reward_multiplier=reward_multiplier,
                                             reward_multiplier_limit=reward_multiplier_limit,
                                             logger=logger,
                                             experience_replay=experience_replay,
                                             )
        self.need_state = True

    def _compute_expected_state_action_values(self, batch_next_states, batch_rewards):
        # using the target policy get the next state values "argmax_a'Q(s_t+1, a', theta)". theta = action-value policy,
        # a' is the value by which we have argmax value in the Q
        next_state_action_values = self.action_value_network(batch_next_states)

        # instead of using argmax I use max because max returns a tuple where the second element is the index of the max
        action_max_indexes = next_state_action_values.max(dim=1)[1]

        # feed the target network with the batch of next states
        next_state_target_values = self.target_network(batch_next_states)
        # filter next_state_target_values using the index of the argmax -> action_max_indexes
        next_state_target_values = next_state_target_values.gather(1, action_max_indexes.unsqueeze(1))
        # to match the size of the batch_rewards squeeze next_state_target_values
        next_state_target_values = next_state_target_values.squeeze(1)

        # compute the expected state action values used as target for computing the loss "y"
        # argmax of next is not necessary, it has been done in the computation of next_state_action_values
        expected_state_action_values = batch_rewards + (next_state_target_values * self._gamma)
        # the results is unsqueeze to match the size of the state_action_values
        return expected_state_action_values.unsqueeze(1)
