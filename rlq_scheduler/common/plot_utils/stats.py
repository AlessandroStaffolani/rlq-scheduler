import os

import numpy as np
import pandas as pd
import scipy.stats as st
from rlq_scheduler.common.object_handler.minio_handler import MinioObjectHandler
from rlq_scheduler.common.stats import RunStats


def print_status(current, total, pre_message='', loading_len=20):
    perc = int((current * 20) / total)
    message = f'{pre_message}:\t{"#" * perc}{"." * (loading_len - perc)}\t{current}/{total}'
    print(message, end='\r')


def load_agents_data(
        agents_data: dict,
        handler: MinioObjectHandler,
        result_folder: str,
        mode='train'
):
    for agent_name, agent_info in agents_data.items():
        print(f'Loading runs name for agent {agent_name}')
        result_path = os.path.join(result_folder, "results", mode, agent_name)
        agent_info['runs_names'] = handler.list_objects_name(f'{result_path}/', recursive=False)
        print(f'Loading {len(agent_info["runs_names"])} runs for agent {agent_name}')
        for i, run_path in enumerate(agent_info['runs_names']):
            agent_info['runs_stats'].append(RunStats.from_dict(handler.load(run_path)))
            print_status(i + 1, len(agent_info['runs_names']), f'Loading agent runs')
        print(f'\nLoaded all the {len(agent_info["runs_names"])} runs for agent {agent_name}')
    return agents_data


def get_parameter_aggregated(data, aggregation, *aggregation_args, **aggregation_kwargs):
    np_data = np.array(data, dtype=np.float)
    try:
        method = getattr(np_data, aggregation)
        return method(*aggregation_args, **aggregation_kwargs)
    except AttributeError:
        return np_data


def get_stats_dataframe(agents_data: dict, parameter: dict):
    columns = [parameter['label'], 'agent', 'epsilon_start', 'c', 'delta', 'lr', 'layers', 'seed', 'reward_multiplier',
               'run_code']
    data = []
    for agent_name, info in agents_data.items():
        for stats in info['runs_stats']:
            param_data = stats.execution_history_stats[parameter['name']]
            if 'skip' in parameter and parameter['skip'] > 0:
                param_data = param_data[parameter['skip'] + 1:]
            row = [
                get_parameter_aggregated(param_data, parameter['aggregation']),
                agent_name,
                None,
                None,
                None,
                None,
                None,
                int(stats.agent_stats['agent_parameters']['agent_seed']),
                int(stats.agent_stats['agent_parameters']['reward_multiplier']),
                stats.run_code
            ]
            if agent_name == "MultiArmedBandit_EpsilonGreedyDecay":
                epsilon = stats.agent_stats['agent_parameters']['policy']['\u03B5']
                epsilon_start = float(epsilon.split('_')[1].split('=')[1])
                row[2] = epsilon_start
            elif agent_name == 'MultiArmedBandit_UCB':
                row[3] = float(stats.agent_stats['agent_parameters']['policy']['c'])
            elif agent_name == 'LinUCB':
                row[4] = float(stats.agent_stats['agent_parameters']['delta'])
            elif agent_name == 'DoubleDQN':
                row[5] = float(stats.agent_stats['agent_parameters']['learning_rate'])
                row[6] = int(stats.agent_stats['agent_parameters']['network_layers'])
            data.append(row)

    return pd.DataFrame(data, columns=columns)


def get_execution_cost_dataframe(agents_data: dict, skip=0):
    columns = ['total_exec_cost', 'agent', 'epsilon_start', 'c', 'delta', 'lr', 'layers', 'seed', 'reward_multiplier']
    data = []
    for agent_name, info in agents_data.items():
        for stats in info['runs_stats']:
            exec_cost_len = len(stats.execution_history_stats['execution_cost'])
            exec_time_len = len(stats.execution_history_stats['execution_time'])
            exec_time_arr = stats.execution_history_stats['execution_time']
            exec_cost_arr = stats.execution_history_stats['execution_cost']
            if exec_time_len != exec_cost_len:
                if exec_cost_len > exec_time_len:
                    exec_cost_arr = stats.execution_history_stats['execution_cost'][0:exec_time_len]
                else:
                    exec_time_arr = stats.execution_history_stats['execution_time'][0:exec_cost_len]
            if skip > 0:
                exec_cost_arr = exec_cost_arr[skip + 1:]
                exec_time_arr = exec_time_arr[skip + 1:]
            exec_cost = np.array(exec_cost_arr, dtype=np.float)
            exec_time = np.array(exec_time_arr, dtype=np.float)
            cost = exec_cost * exec_time
            row = [
                cost.sum(),
                agent_name,
                None,
                None,
                None,
                None,
                None,
                int(stats.agent_stats['agent_parameters']['agent_seed']),
                int(stats.agent_stats['agent_parameters']['reward_multiplier'])
            ]
            if agent_name == "MultiArmedBandit_EpsilonGreedyDecay":
                epsilon = stats.agent_stats['agent_parameters']['policy']['\u03B5']
                epsilon_start = float(epsilon.split('_')[1].split('=')[1])
                row[2] = epsilon_start
            elif agent_name == 'MultiArmedBandit_UCB':
                row[3] = float(stats.agent_stats['agent_parameters']['policy']['c'])
            elif agent_name == 'LinUCB':
                row[4] = float(stats.agent_stats['agent_parameters']['delta'])
            elif agent_name == 'DoubleDQN':
                row[5] = float(stats.agent_stats['agent_parameters']['learning_rate'])
                row[6] = int(stats.agent_stats['agent_parameters']['network_layers'])
            data.append(row)

    return pd.DataFrame(data, columns=columns)


def get_waiting_cost_dataframe(agents_data: dict, skip=0):
    columns = ['total_waiting_cost', 'agent', 'epsilon_start', 'c', 'delta', 'lr', 'layers', 'seed', 'reward_multiplier']
    data = []
    for agent_name, info in agents_data.items():
        for stats in info['runs_stats']:
            wait_cost_len = len(stats.execution_history_stats['waiting_cost'])
            wait_time_len = len(stats.execution_history_stats['waiting_time'])
            wait_time_arr = stats.execution_history_stats['waiting_time']
            wait_cost_arr = stats.execution_history_stats['waiting_cost']
            if wait_time_len != wait_cost_len:
                if wait_cost_len > wait_time_len:
                    wait_cost_arr = stats.execution_history_stats['waiting_cost'][0:wait_time_len]
                else:
                    wait_time_arr = stats.execution_history_stats['waiting_time'][0:wait_cost_len]
            if skip > 0:
                wait_cost_arr = wait_cost_arr[skip + 1:]
                wait_time_arr = wait_time_arr[skip + 1:]
            waiting_cost = np.array(wait_cost_arr, dtype=np.float)
            waiting_time = np.array(wait_time_arr, dtype=np.float)
            cost = waiting_cost * waiting_time
            row = [
                cost.sum(),
                agent_name,
                None,
                None,
                None,
                None,
                None,
                int(stats.agent_stats['agent_parameters']['agent_seed']),
                int(stats.agent_stats['agent_parameters']['reward_multiplier'])
            ]
            if agent_name == "MultiArmedBandit_EpsilonGreedyDecay":
                epsilon = stats.agent_stats['agent_parameters']['policy']['\u03B5']
                epsilon_start = float(epsilon.split('_')[1].split('=')[1])
                row[2] = epsilon_start
            elif agent_name == 'MultiArmedBandit_UCB':
                row[3] = float(stats.agent_stats['agent_parameters']['policy']['c'])
            elif agent_name == 'LinUCB':
                row[4] = float(stats.agent_stats['agent_parameters']['delta'])
            elif agent_name == 'DoubleDQN':
                row[5] = float(stats.agent_stats['agent_parameters']['learning_rate'])
                row[6] = int(stats.agent_stats['agent_parameters']['network_layers'])
            data.append(row)

    return pd.DataFrame(data, columns=columns)


def get_runtime_dataframe(agents_data: dict, skip=0):
    columns = ['runtime', 'agent', 'epsilon_start', 'c', 'delta', 'lr', 'layers', 'seed', 'reward_multiplier']
    data = []
    for agent_name, info in agents_data.items():
        for stats in info['runs_stats']:
            runtime = float(stats.global_stats['end_execution_time']) \
                      - float(stats.global_stats['start_execution_time'])
            if skip > 0:
                runtime = runtime[skip + 1:]
            row = [
                runtime,
                agent_name,
                None,
                None,
                None,
                None,
                None,
                int(stats.agent_stats['agent_parameters']['agent_seed']),
                int(stats.agent_stats['agent_parameters']['reward_multiplier'])
            ]
            if agent_name == "MultiArmedBandit_EpsilonGreedyDecay":
                epsilon = stats.agent_stats['agent_parameters']['policy']['\u03B5']
                epsilon_start = float(epsilon.split('_')[1].split('=')[1])
                row[2] = epsilon_start
            elif agent_name == 'MultiArmedBandit_UCB':
                row[3] = float(stats.agent_stats['agent_parameters']['policy']['c'])
            elif agent_name == 'LinUCB':
                row[4] = float(stats.agent_stats['agent_parameters']['delta'])
            elif agent_name == 'DoubleDQN':
                row[5] = float(stats.agent_stats['agent_parameters']['learning_rate'])
                row[6] = int(stats.agent_stats['agent_parameters']['network_layers'])
            data.append(row)

    return pd.DataFrame(data, columns=columns)


def create_aggregated_reward_df(agent_data, window_size=50):
    data = []
    columns = ['cumulative_reward', 'reward', 'timestep', 'seed', 'delta', 'agent_name', 'run_code']
    for agent_name, info in agent_data.items():
        for stats in info['runs_stats']:
            seed = int(stats.agent_stats['agent_parameters']['agent_seed'])
            if agent_name == 'LinUCB':
                delta = float(stats.agent_stats['agent_parameters']['delta'])
            else:
                delta = None
            run_code = stats.run_code
            cum_reward = 0
            cum_window = []
            rew_window = []
            for i, reward in enumerate(stats.execution_history_stats['reward']):
                cum_reward += float(reward)
                cum_window.append(cum_reward)
                rew_window.append(float(reward))
                if i % window_size == 0:
                    cum_avg = sum(cum_window)/len(cum_window)
                    rew_avg = sum(rew_window)/len(rew_window)
                    time_step = i // window_size
                    data.append([
                        cum_avg,
                        rew_avg,
                        time_step,
                        seed,
                        delta,
                        agent_name,
                        run_code
                    ])
                    cum_window = []
                    rew_window = []

    return pd.DataFrame(data=data, columns=columns)


def get_assignment_history_df(agents_data, window_size=25):
    data = []
    for agent_name, info in agents_data.items():
        for stats in info['runs_stats']:
            history = stats.execution_history_stats['assignments_history']
            window_arr = []
            count = 0
            step_count = 0
            cumulative_reward = 0
            for entry in history:
                if entry['reward'] is not None:
                    window_arr.append(entry['reward'])
                    count += 1
                    if count % window_size == 0:
                        reward = np.array(window_arr, dtype=np.float64).mean()
                        cumulative_reward += reward
                        data.append({
                            'reward': reward,
                            'cumulative_reward': cumulative_reward,
                            'time_step': step_count,
                            'phase': entry['phase'],
                            'agent': agent_name,
                            'run_code': stats.run_code
                        })
                        step_count += 1
                        window_arr = []
                        count = 0
    return pd.DataFrame(data)


def arr_confidence_interval(data, confidence=0.95):
    a = 1.0 * data
    n = len(a)
    m, se = np.mean(a), st.sem(a)
    h = se * st.t.ppf((1 + confidence) / 2., n-1)
    return h


def print_mean_and_ci(df, agent, params, is_max=False):
    if len(params) == 1:
        df_filtered = df[(df.agent == agent) & (df.delta == params[0])]
    else:
        df_filtered = df[(df.agent == agent) & (df.lr == params[0]) & (df.layers == params[1])]
    avg = df_filtered.total_reward.mean()
    ci = arr_confidence_interval(df_filtered.total_reward.to_numpy())
    print_str = f'{np.round(avg, 3)} $\pm$ {np.round(ci, 3)}'
    if is_max:
        print_str = '\textbf{' + print_str + '}'
    return print_str


def get_mean_and_ci(df, agent, params):
    if len(params) == 1:
        df_filtered = df[(df.agent == agent) & (df.delta == params[0])]
    else:
        df_filtered = df[(df.agent == agent) & (df.lr == params[0]) & (df.layers == params[1])]
    avg = df_filtered.total_reward.mean()
    ci = arr_confidence_interval(df_filtered.total_reward.to_numpy())
    return avg, ci


def get_table(reward_name, df, agent_name, name_1, params_1, name_2=None, params_2=None):
    if name_2 is None and params_2 is None:
        columns = pd.MultiIndex.from_product([name_1, params_1])
    else:
        columns = pd.MultiIndex.from_product([name_1, params_1, name_2, params_2])

    index = pd.MultiIndex.from_product([[reward_name], ['R', 'ci']])
    data = []
    for col in columns:
        if len(col) == 2:
            # LinUCB
            avg, ci = get_mean_and_ci(df, agent_name, (col[1], ))
            data.append([np.round(avg, 3), f'$\pm {np.round(ci, 3)}$'])
        elif len(col) == 4:
            # DoubleDQN
            avg, ci = get_mean_and_ci(df, agent_name, (col[3], col[1]))
            data.append([np.round(avg, 3), f'$\pm {np.round(ci, 3)}$'])
    np_data = np.array(data)
    return pd.DataFrame(np_data.transpose(), columns=columns, index=index)
