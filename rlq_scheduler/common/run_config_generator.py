import itertools
import os
from copy import deepcopy

from rlq_scheduler.common.config_helper import TrajectoryCollectorConfigHelper, MultiRunConfigHelper, RunConfigHelper
from rlq_scheduler.common.run_config import RunConfig


def prepare_runs_config(seeds, multi_run_config: MultiRunConfigHelper, config_folder,
                        run_config_example: RunConfigHelper = None):
    if run_config_example is None:
        run_config_template = _load_config(config_folder=config_folder,
                                           conf_type=RunConfigHelper,
                                           filename='run_config.yml')
    else:
        run_config_template = run_config_example.config

    runs_config = []

    for seed in seeds['agent']:
        run_config = deepcopy(run_config_template)
        _prepare_global_config(
            config=multi_run_config,
            run_config=run_config,
            agent_seed=seed,
            task_generator_seed=seeds['task_generator'],
            runs_config=runs_config)
    return runs_config


def prepare_runs_random_seeds(random_generator, multi_run_config: MultiRunConfigHelper):
    seeds = {
        'task_generator': None,
        'agent': []
    }
    if multi_run_config.auto_generate_seeds() is True:
        # auto generate seeds
        if multi_run_config.n_runs() > 0:
            seeds_generated = random_generator.choice(1000, multi_run_config.n_runs() + 1, replace=False).tolist()
            seeds['task_generator'] = seeds_generated[0]
            seeds['agent'] = seeds_generated[1:]
    else:
        seeds['task_generator'] = multi_run_config.task_generator_seed()
        seeds['agent'] = multi_run_config.agent_seeds()
    return seeds


def _prepare_trajectory_collector_config(config_folder):
    tc_config = _load_config(config_folder, TrajectoryCollectorConfigHelper, 'trajectory_collector.yml')
    return deepcopy(tc_config)


def _prepare_global_config(config: MultiRunConfigHelper,
                           run_config,
                           agent_seed,
                           task_generator_seed,
                           runs_config):
    run_config['task_generator']['random_seed'] = task_generator_seed
    run_config['task_generator']['bootstrapping'] = config.tasks_to_bootstrap()
    run_config['task_generator']['tasks_to_generate'] = config.tasks_to_generate()
    if config.save_properties() is not None:
        run_config['global']['save_properties'] = config.save_properties()
    if config.penalties() is not None:
        run_config['global']['penalties'] = config.penalties()
    if config.functions() is not None:
        run_config['global']['functions'] = config.functions()
    for global_features in config.features_enabled():
        # set global feature
        for feature, value in global_features.items():
            run_config['global']['features_enabled'][feature] = value

        _prepare_state_and_context_features(
            config=config,
            run_config=run_config,
            agent_seed=agent_seed,
            runs_config=runs_config
        )


def _prepare_state_and_context_features(config: MultiRunConfigHelper,
                                        run_config,
                                        agent_seed,
                                        runs_config):
    state_features = config.state_features()
    context_features = config.context_features()
    state_window_size = config.state_window_size()
    run_config['global']['state']['time_window'] = state_window_size
    run_config['global']['context']['features'] = context_features
    for features in state_features:
        run_config['global']['state']['features'] = features
        _prepare_agent_global_config(
            config=config,
            run_config=run_config,
            agent_seed=agent_seed,
            runs_config=runs_config
        )


def _prepare_agent_global_config(config: MultiRunConfigHelper,
                                 run_config,
                                 agent_seed,
                                 runs_config):
    for agent_c in config.agents_config():
        run_config['agent']['global'] = deepcopy(config.global_agent_config())
        run_config['agent']['global']['random_seed'] = agent_seed

        run_config['global']['features_enabled']['agent_type']['name'] = agent_c['type']
        if 'policy' in agent_c:
            run_config['global']['features_enabled']['agent_type']['policy'] = agent_c['policy']
        else:
            run_config['global']['features_enabled']['agent_type']['policy'] = None

        if 'policy_parameters' in agent_c and 'policy' in agent_c:
            for param, value in agent_c['policy_parameters'].items():
                run_config['agent']['policies_parameters'][agent_c['policy']][param] = value

        if agent_c['type'] == 'lin-ucb':
            run_config['global']['features_enabled']['context'] = True
        else:
            run_config['global']['features_enabled']['context'] = False

        if agent_c['type'] == 'double-dqn' or agent_c['type'] == 'dqn':
            run_config['agent']['agents_parameters'][agent_c['type']]['batch_size'] = agent_c['batch_size']
            run_config['agent']['agents_parameters'][agent_c['type']]['epsilon'] = agent_c['epsilon']
            run_config['agent']['agents_parameters'][agent_c['type']]['experience_replay_capacity'] = agent_c[
                'experience_replay_capacity']
            run_config['agent']['agents_parameters'][agent_c['type']]['gamma'] = agent_c['gamma']
            run_config['agent']['agents_parameters'][agent_c['type']]['network_config'] = agent_c['network_config']
            run_config['agent']['agents_parameters'][agent_c['type']]['optimizer'] = agent_c['optimizer']
            run_config['agent']['agents_parameters'][agent_c['type']]['target_net_update_frequency'] = agent_c[
                'target_net_update_frequency']

        for p_name, p_value in agent_c.items():
            if p_name != 'parameters' and p_name != 'type' and p_name != 'policy':
                run_config['agent']['agents_parameters'][agent_c['type']][p_name] = deepcopy(p_value)

        agent_combinations = generate_combinations(agent_c['parameters'])
        for i, params_combination in enumerate(agent_combinations):
            _prepare_agent_config(
                run_config=run_config,
                runs_config=runs_config,
                params_combination=params_combination
            )


def _prepare_agent_config(
        run_config,
        runs_config,
        params_combination):
    switcher = {
        'agent': set_agent_config,
        'policy': set_policy_config,
        'policy_param': set_policy_param_config,
        'agent_parameter_param': set_agent_parameter_param,
        'agent_global': set_agent_global_param,
        'agent_global_param': set_agent_global_param
    }
    if len(params_combination) > 0:
        for param in params_combination:
            param_type = param[2]
            parameter_param_name = param[3]
            seed_override = param[4]
            if param_type in switcher:
                switcher[param_type](run_config, key=param[0], value=param[1],
                                     parameter_param_name=parameter_param_name,
                                     agent_type=run_config['global']['features_enabled']['agent_type']['name'],
                                     policy_type=run_config['global']['features_enabled']['agent_type']['policy'],
                                     seed_override=seed_override
                                     )
        runs_config.append(RunConfig(run_config=deepcopy(run_config)))
    else:
        runs_config.append(RunConfig(run_config=deepcopy(run_config)))


def _load_config(config_folder, conf_type, filename):
    config_path = os.path.join(config_folder, filename)
    return conf_type(config_path=config_path).config


def set_agent_config(config, key, value, parameter_param_name=None, agent_type='', policy_type='', seed_override=None):
    config['agent']['agents_parameters'][agent_type][key] = value


def set_policy_config(config, key, value, parameter_param_name=None, agent_type='', policy_type='', seed_override=None):
    config['agent']['policies_parameters'][policy_type][key] = value


def set_policy_param_config(config, key, value, parameter_param_name=None, agent_type='', policy_type='',
                            seed_override=None):
    config['agent']['policies_parameters'][policy_type][parameter_param_name]['parameters'][key] = value


def set_agent_parameter_param(config, key, value, parameter_param_name=None, agent_type='', policy_type='',
                              seed_override=None):
    config['agent']['agents_parameters'][agent_type][parameter_param_name]['parameters'][key] = value


def set_agent_global_param(config, key, value, parameter_param_name=None, agent_type='', policy_type='',
                           seed_override=None):
    if parameter_param_name is not None:
        config['agent']['global'][parameter_param_name][key] = value
    else:
        config['agent']['global'][key] = value

    if parameter_param_name == 'load_model_config':
        config['agent']['global'][parameter_param_name]['load'] = True

    if seed_override is not None:
        config['agent']['global']['random_seed'] = seed_override


def generate_combinations(parameters):
    """
    Generate combinations of parameters depending on the config presents in the `parameters` array of dictionary
    Parameters
    ----------
    parameters: list()
        list of parameter dictionary configurations
    Returns
    -------
    list()
        return an array with the combinations that has to be used for the hyperparameter tuning.
        Each item in the list will be a tuple representing one combination to be executed. Each element of the tuple
        represent a single parameter and it is a tuple itself of size 2, where the first element is the name of
        the parameter and the second is the value
    """
    # use mode as key, and as value a function that perform the operations necessary for that mode
    switcher = {
        'linear': __generate_linear_combinations
    }

    possibilities = []
    # I need to use itertools.combinatinos to generate all the possible combinations
    for param_config in parameters:
        parameter_param_name = None
        if 'param' in param_config:
            parameter_param_name = param_config['param']
        if param_config['mode'] == 'array':
            if 'seed' in param_config:
                seed = param_config['seed']
            else:
                seed = None
            possibilities.append([(param_config['name'], value, param_config['type'], parameter_param_name, seed)
                                  for value in param_config['values']])
        else:
            generater_func = switcher[param_config['mode']]
            possibilities.append(generater_func(param_config, parameter_param_name))

    return list(itertools.product(*possibilities))


def count_total_combinations(config):
    combinations = 0
    for agent_config in config['agents']:
        combinations += len(generate_combinations(agent_config['parameters']))
    return combinations


def __generate_linear_combinations(param_config, parameter_param_name):
    """
    Generate combination for the linear case.
    Parameters
    ----------
    param_config: dict
        dictionary with the configuration for a linear combinations. It must have the following properties:
            - type: type of the parameter that could be ['gloabl', 'agent', 'policy']
            - name: name of the parameter
            - min: min value for the parameter
            - max: max value for the parameter, max will be always included as parameter value at the end, even if the
                step cause to skip it
            - step: step value used to go from min to max
    Returns
    -------
    list()
        return an array with the possible value in the range specified, that has to be used for the
        hyperparameter tuning. Each item in the list will be a tuple of size 2, where the first element is the name of
        the parameter and the second is the value
    """
    param_type = param_config['type']
    name = param_config['name']
    min_value = param_config['min']
    max_value = param_config['max']
    step = param_config['step']
    possibilities = []
    value = min_value
    while value <= max_value:
        possibilities.append((name, value, param_type, parameter_param_name, None))
        value += step
    if value != (max_value + step):
        possibilities.append((name, max_value, param_type, parameter_param_name, None))
    return possibilities
