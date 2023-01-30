import pickle
from copy import deepcopy

from rlq_scheduler.agent.agents.base import BaseAgent
from rlq_scheduler.agent.agents.contextual_bandit.contextual_bandit import LinUCBAgent
from rlq_scheduler.agent.agents.baselines.lru import LRUAgent
from rlq_scheduler.agent.agents.baselines.e_pvm import EPVMAgent
from rlq_scheduler.agent.agents.reinforcement_learning.dqn_agent import DQNAgent, DoubleDQNAgent
from rlq_scheduler.common.config_helper import GlobalConfigHelper, RunConfigHelper
from rlq_scheduler.common.experience_replay.experience_replay import ExperienceReplay

DQN_MODEL_AGENTS = [DQNAgent, DoubleDQNAgent]


def serialize_agent(agent):
    """
    Serialize an agent
    Parameters
    ----------
    agent: BaseAgent
        agent to be serialized
    """
    return pickle.dumps(agent.get_serializable_content(), protocol=pickle.HIGHEST_PROTOCOL)


def deserialize_agent(serialized_agent):
    """
    De-serialize an agent
    Parameters
    ----------
    serialized_agent:
        Serialized agent
    Returns
    -------
    BaseAgent
        agent obtained by the de-serialization of the file
    """
    return pickle.loads(serialized_agent)


def get_agent_model_to_load(agent_config):
    if agent_config['load_model_config']['load'] is True:
        if agent_config['load_model_config']['path'] is not None:
            return agent_config['load_model_config']['path']
        else:
            raise AttributeError('Agent load model is enabled but path is None')
    else:
        return None


def create_agent_from_config(agent_config,
                             global_config: GlobalConfigHelper,
                             run_config: RunConfigHelper,
                             agent_model=None,
                             external_workers_config=None,
                             logger=None,
                             experience_replay: ExperienceReplay = None
                             ):
    """
    Static method for create an agent from the configs
    Parameters
    ----------
    agent_config: dict
        agent config
    global_config: GlobalConfigHelper
        configuration of the environment
    run_config: RunConfigHelper
        configuration of the current run
    agent_model:
        deserialized model loaded from the object handler or None
    external_workers_config: dict
        worker_external feature config
    logger: logger | None
        logger used by the agent
    experience_replay: ExperienceReplay
    Returns
    -------
    BaseAgent
        the agent created
    """
    available_agents = {
        'random': BaseAgent,
        'lin-ucb': LinUCBAgent,
        'dqn': DQNAgent,
        'double-dqn': DoubleDQNAgent,
        'lru': LRUAgent,
        'e-pvm': EPVMAgent,
    }
    agent_parameters = deepcopy(agent_config)
    agent_parameters['action_space'] = run_config.available_worker_classes()
    agent_class = available_agents[agent_parameters['type']]
    del agent_parameters['type']
    del agent_parameters['load_model_config']
    if 'reward_multiplier' in agent_parameters and 'value' in agent_parameters['reward_multiplier'] and \
            'limit' in agent_parameters['reward_multiplier']:
        agent_parameters['reward_multiplier_limit'] = agent_parameters['reward_multiplier']['limit']
        agent_parameters['reward_multiplier'] = agent_parameters['reward_multiplier']['value']
    agent_parameters['model_to_load'] = agent_model
    agent_parameters['external_workers_config'] = external_workers_config
    agent_parameters['global_config'] = global_config
    agent_parameters['run_config'] = run_config
    agent_parameters['logger'] = logger
    agent_parameters['experience_replay'] = experience_replay
    return agent_class(**agent_parameters)
