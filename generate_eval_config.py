import os
from copy import deepcopy

import numpy as np
import pandas as pd

from rlq_scheduler.common.config_helper import MultiRunConfigHelper, GlobalConfigHelper
from rlq_scheduler.common.object_handler import create_object_handler, MinioObjectHandler
from rlq_scheduler.common.plot_utils.stats import get_stats_dataframe, load_agents_data, print_status
from rlq_scheduler.common.stats import RunStats
from rlq_scheduler.common.trajectory_saver.database import Database
from rlq_scheduler.common.utils.filesystem import save_file, ROOT_DIR
from rlq_scheduler.common.utils.logger import get_logger

RESULT_FOLDER = 'waiting-time'
RESULT_FOLDER_OUTPUT = 'eval-new-waiting-time'

OUTPUT_FILES = 'config/kube/deployments/waiting-time/new'

MINIO_BUCKET = 'gtraces1'

AGENT_NAME = 'DoubleDQN'
AGENT_CODE = 'double-dqn'
AGENT_PARAM = ('lr', 'layers')

LOAD_SEEDS_FROM_DB = None  # or None
DB_NAME = 'sb_waiting_time'
DB_COLLECTION = 'waiting-time'

PARAM_NAME_MAPPING = {
    'delta': 'delta',
    'lr': 'learning_rate',
    'layers': 'network_config.parameters.hidden_layers'
}

PARAM_NAME_TYPE_MAPPING = {
    'delta': float,
    'lr': float,
    'layers': int
}

TASK_GENERATOR_SEED = 200
N_TASKS = 13730
N_BOOTSTRAP_TASKS = 0
REWARD_FUNCTION = 'waiting-time'
REWARD_FUNCTION_PARAMETERS = {}
LOAD_MODEL = False
TRAIN = True
ADD_BASELINES = False
AGENT_PARAMETERS = {
    'LinUCB': {
        'type': AGENT_CODE,
        'delta': 2,
        'parameters': [
            {
                'type': 'agent_global',
                'name': 'path',
                'param': 'load_model_config',
                'mode': 'array',
                'seed': None,
                'values': []
            }
        ]
    },
    'DoubleDQN': {
        'type': AGENT_CODE,
        'experience_replay_capacity': 4000,
        'learning_rate': 0.001,
        'gamma': 0.99,
        'batch_size': 64,
        'target_net_update_frequency': 400,
        'epsilon': {
            'type': 'linear-decay',
            'parameters': {'start': 0.65, 'end': 0.1, 'total': 6000}
        },
        'optimizer': 'adam',
        'network_config': {
            'type': 'fully-connected',
            'parameters': {'hidden_layers': 3}
        },
        'parameters': [
            {
                'type': 'agent_global',
                'name': 'path',
                'param': 'load_model_config',
                'mode': 'array',
                'seed': None,
                'values': []
            }
        ]
    }
}

agents = {
    AGENT_NAME: {
        'runs_names': [],
        'runs_stats': []
    }}

BASELINE_PARAMETERS = {
    'type': 'agent_global',
    'name': 'random_seed',
    'mode': 'array',
    'seed': None,
    'values': []
}

test_runs = [
    {'seed': 3,
     'run_code': '6c47d1b6-fceb-44d2-9c59-3ead3f745dc9',
     'total_reward': -9924.397213935852},
    {'seed': 4,
     'run_code': 'e723d898-a9b4-463d-89f0-5ccbe7322733',
     'total_reward': -26692.695888996124},
    {'seed': 5,
     'run_code': '38b287b7-338a-4d5d-a2a9-a2b7f39a969e',
     'total_reward': -20220.14770269394},
    {'seed': 6,
     'run_code': '91002ee0-57e1-4b12-9729-79cf95643668',
     'total_reward': -16641.10775566101},
    {'seed': 7,
     'run_code': 'e7e2a640-36ce-497c-bb91-1aeb2ceddaa3',
     'total_reward': -61731.80339550972}
]

test_param = (2.0, 3)


def set_best_params(agent_config, parameters):
    if isinstance(parameters, float) or isinstance(parameters, np.float64):
        # single param
        p_name = AGENT_PARAM
        p_type = PARAM_NAME_TYPE_MAPPING[p_name]
        p_value = p_type(parameters)
        set_param_value(agent_config, p_value, p_name)
    elif isinstance(parameters, tuple):
        for i, p in enumerate(parameters):
            p_name = AGENT_PARAM[i]
            p_type = PARAM_NAME_TYPE_MAPPING[p_name]
            p_value = p_type(p)
            set_param_value(agent_config, p_value, p_name)


def set_param_value(agent_config, p_value, p_name):
    mapping = PARAM_NAME_MAPPING[p_name]
    if '.' not in mapping:
        agent_config[mapping] = p_value
    else:
        parts = mapping.split('.')
        nested = None
        for p in parts[0:-1]:
            if nested is None:
                nested = agent_config[p]
            else:
                nested = nested[p]
        nested[parts[-1]] = p_value


def param_to_array(parameters):
    if isinstance(parameters, float) or isinstance(parameters, np.float64) or isinstance(parameters, str):
        # single param
        return [parameters]
    elif isinstance(parameters, tuple):
        return list(parameters)


def filter_df(df, agent_name, best_p):
    if agent_name == 'LinUCB':
        return df[df.delta == best_p]
    elif agent_name == 'DoubleDQN':
        return df[(df.lr == best_p[0]) & (df.layers == best_p[1])]


def load_agents_data_from_run_seeds_and_db(
        agents_data: dict,
        object_handle: MinioObjectHandler,
        result_folder: str,
        database: Database,
        db_name: str,
        collection: str,
        seeds: list,
        mode='train'
):
    for agent_name, agent_info in agents_data.items():
        print(f'Loading runs name for agent {agent_name}')

        runs_codes = [r['run_code'] for r in database.client[db_name][collection].find({
            'agent_parameters.agent_seed': {'$in': seeds}, 'agent_type': agent_name})]
        paths_to_load = []
        full_path = os.path.join(result_folder, "results", mode, agent_name)
        folder_files = handler.list_objects_name(f'{full_path}/')
        for path in folder_files:
            code = path.split('/')[-1].split('_')[0]
            if code in runs_codes:
                paths_to_load.append(path)

        agent_info['runs_names'] = paths_to_load
        print(f'Loading {len(agent_info["runs_names"])} runs for agent {agent_name}')
        for i, run_path in enumerate(agent_info['runs_names']):
            agent_info['runs_stats'].append(RunStats.from_dict(object_handle.load(run_path)))
            print_status(i + 1, len(agent_info['runs_names']), f'Loading agent runs')
        print(f'\nLoaded all the {len(agent_info["runs_names"])} runs for agent {agent_name}')
    return agents_data


def load_agents_data_efficient(
        agents_data: dict,
        o_handler: MinioObjectHandler,
        result_folder: str,
        mode='train'
):
    dfs = []
    for agent_name, agent_info in agents_data.items():
        print(f'Loading runs name for agent {agent_name}')
        result_path = os.path.join(result_folder, "results", mode, agent_name)
        agent_info['runs_names'] = o_handler.list_objects_name(f'{result_path}/', recursive=False)
        print(f'Loading {len(agent_info["runs_names"])} runs for agent {agent_name}')
        for i, run_path in enumerate(agent_info['runs_names']):
            stats = RunStats.from_dict(o_handler.load(run_path))
            agent_info['runs_stats'] = [stats]
            dfs.append(get_stats_dataframe(
                agents,
                {
                    'label': 'total_reward',
                    'name': 'reward',
                    'aggregation': 'sum',
                    'skip': 2999 if AGENT_CODE == 'double-dqn' else 0
                }
            ))
            print_status(i + 1, len(agent_info['runs_names']), f'Loading agent runs')
        print(f'\nLoaded all the {len(agent_info["runs_names"])} runs for agent {agent_name}')
    return pd.concat(dfs, ignore_index=True)


if __name__ == '__main__':
    global_config = GlobalConfigHelper(config_path='config/global.yml')
    global_config.config['object_handler']['default_bucket'] = MINIO_BUCKET
    logger = get_logger(global_config.logger())
    handler = create_object_handler(global_config, logger)
    db = Database(global_config, logger)
    logger.info('Starting results loading')
    if LOAD_SEEDS_FROM_DB is not None:
        agents = load_agents_data_from_run_seeds_and_db(
            agents, handler, RESULT_FOLDER, db, DB_NAME, DB_COLLECTION, LOAD_SEEDS_FROM_DB)
        rewards_df = get_stats_dataframe(
            agents,
            {
                'label': 'total_reward',
                'name': 'reward',
                'aggregation': 'sum',
                'skip': 2999 if AGENT_CODE == 'double-dqn' else 0
            }
        )
    else:
        rewards_df = load_agents_data_efficient(agents, handler, RESULT_FOLDER)
    agent_df = rewards_df[rewards_df.agent == AGENT_NAME]
    agent_no_multi_df = agent_df[agent_df.reward_multiplier == 1]
    print(f'Best {AGENT_NAME} without reward multiplier param and best param run codes\n')
    best_param = agent_no_multi_df.groupby(param_to_array(AGENT_PARAM)).total_reward.mean().idxmax()
    best_value = agent_no_multi_df.groupby(param_to_array(AGENT_PARAM)).total_reward.mean().max()
    print('best param: \t\t{}\t\t\t\t\t\t max mean: \t{}'.format(best_param, best_value))
    print('------------------------')
    best_runs = []
    filtered_df = filter_df(agent_no_multi_df, AGENT_NAME, best_param)
    for _, value in filtered_df.iterrows():
        best_runs.append({'seed': value.seed, 'run_code': value.run_code, 'total_reward': value.total_reward})
    best_runs.sort(key=lambda x: x['seed'])
    for value in best_runs:
        print(f'seed {value["seed"]} run code: \t{value["run_code"]}\t\t reward: \t{value["total_reward"]}')

    template = MultiRunConfigHelper(config_path='config/multi_run_config.yml')
    config = deepcopy(template.config)
    config['global']['seeds']['auto'] = False
    config['global']['seeds']['n_runs'] = 1
    config['global']['seeds']['task_generator'] = TASK_GENERATOR_SEED
    config['global']['seeds']['agents'] = [3]
    config['task_generator']['bootstrapping']['tasks_to_generate'] = N_BOOTSTRAP_TASKS
    config['task_generator']['tasks_to_generate'][0]['tasks_to_generate'] = N_TASKS
    config['save_properties']['run_name_prefix'] = RESULT_FOLDER_OUTPUT
    config['functions']['reward_function']['type'] = REWARD_FUNCTION
    config['functions']['reward_function']['extra_parameters'] = REWARD_FUNCTION_PARAMETERS
    config['global_agent_config']['load_model_config']['load'] = LOAD_MODEL
    config['global_agent_config']['train'] = TRAIN
    agents_config = []
    for data in best_runs:
        main_agent_config = deepcopy(AGENT_PARAMETERS[AGENT_NAME])
        set_best_params(main_agent_config, best_param)
        model_path = ''
        files = handler.list_objects_name(f'{RESULT_FOLDER}/models/train/{AGENT_NAME}/{data["run_code"]}')
        main_agent_config['parameters'][0]['values'].append(files[0])
        main_agent_config['parameters'][0]['seed'] = data['seed']
        agents_config.append(main_agent_config)
        if ADD_BASELINES:
            random_parameters = deepcopy(BASELINE_PARAMETERS)
            random_parameters['seed'] = data['seed']
            random_parameters['values'].append(data['seed'])
            random = {'type': 'random', 'parameters': [random_parameters]}
            lru_parameters = deepcopy(BASELINE_PARAMETERS)
            lru_parameters['seed'] = data['seed']
            lru_parameters['values'].append(data['seed'])
            lru = {'type': 'lru', 'parameters': [lru_parameters]}
            agents_config.append(random)
            agents_config.append(lru)
    config['agents'] = agents_config

    save_file(os.path.join(ROOT_DIR, OUTPUT_FILES),
              f'{AGENT_CODE}_eval-config.yml',
              config,
              is_yml=True)

    logger.info(f'Created all the configuration files and saved in {OUTPUT_FILES}')
