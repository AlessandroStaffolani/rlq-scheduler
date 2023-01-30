import json
import os
import time
from collections import namedtuple
from datetime import datetime
from uuid import uuid4

import numpy as np

from rlq_scheduler.common.backends.backend_factory import get_backend_adapter
from rlq_scheduler.common.backends.base_backend import BaseBackend
from rlq_scheduler.common.config_helper import GlobalConfigHelper
from rlq_scheduler.common.utils.encoders import NumpyEncoder


def add_values_to_dict(dict_obj: dict, *args, **kwargs):
    if 0 < len(args) < len(dict_obj):
        for i, key in enumerate(dict_obj.keys()):
            dict_obj[key] = args[i]

    if len(kwargs) > 0:
        for key, val in kwargs.items():
            if key in dict_obj:
                dict_obj[key] = val
    return dict_obj


class AssignmentEntry(
    namedtuple(
        'AssignmentEntry',
        'task_id action worker_class reward task_name time_step phase agent created_at updated_at task_params',
        defaults=[None, None, None, None, None, None, None, None, time.time(), None, None])
):

    def to_dict(self):
        if getattr(self, '_asdict'):
            return self._asdict()
        else:
            new_dict = {}
            keys = self._fields
            index = 0
            for key in keys:
                new_dict[key] = self[index]
                index += 1
            return dict

    def to_json(self):
        return json.dumps(self.to_dict(), cls=NumpyEncoder)


class RunStats:

    def __init__(self, run_code=None):
        self.run_code = run_code if run_code is not None else str(uuid4())
        self.global_stats = {
            'task_generator_seed': None,
            'tasks_to_generate': 0,
            'tasks_distribution_config': None,
            'tasks_to_bootstrap': 0,
            'tasks_bootstrapping_config': None,
            'features_enabled': [],
            'functions': None,
            'state_features': [],
            'context_features': [],
            'task_succeeded': 0,
            'task_failed': 0,
            'validation_reward': [],
            'prepare_time': None,
            'start_execution_time': None,
            'end_execution_time': None,
            'end_time': None
        }
        self.agent_stats = {
            'agent_type': None,
            'agent_parameters': None,
            'agent_model': None
        }
        self.execution_history_stats = {
            'tasks_generated': [],
            'selected_actions': [],
            'single_run_selected_actions': [],
            'assignments_history': [],
            'reward': [],
            'loss': [],
            'epsilon': [],
            'waiting_time': [],
            'waiting_cost': [],
            'execution_time': [],
            'execution_cost': [],
            'full_time_get_action': [],  # time necessary for the TaskBroker to receive the action from the agent
            'full_agent_get_action_time': [],  # time necessary for getting the env state and the action
            'agent_get_action_time': []  # time necessary for the agent to choose the action
        }

    def set_global_stats(self, *args, **kwargs):
        self.global_stats = add_values_to_dict(self.global_stats, *args, **kwargs)

    def set_agent_stats(self, *args, **kwargs):
        self.agent_stats = add_values_to_dict(self.agent_stats, *args, **kwargs)

    def set_execution_history_stats(self, *args, **kwargs):
        self.execution_history_stats = add_values_to_dict(self.execution_history_stats, *args, **kwargs)

    def compute_execution_stats(self):
        try:
            reward = np.array(self.execution_history_stats['reward'], dtype=np.float)
            # avg_validation_cumulative_reward = np.array(
            #     self.execution_history_stats['avg_validation_cumulative_reward'], dtype=np.float)
            waiting_time = np.array(self.execution_history_stats['waiting_time'], dtype=np.float)
            waiting_cost = np.array(self.execution_history_stats['waiting_cost'], dtype=np.float)
            execution_time = np.array(self.execution_history_stats['execution_time'], dtype=np.float)
            execution_cost = np.array(self.execution_history_stats['execution_cost'], dtype=np.float)
            full_time_get_action = np.array(self.execution_history_stats['full_time_get_action'], dtype=np.float)
            full_agent_get_action_time = np.array(self.execution_history_stats['full_agent_get_action_time'],
                                                  dtype=np.float)
            agent_get_action_time = np.array(self.execution_history_stats['agent_get_action_time'], dtype=np.float)
            execution_stats = {
                'total_reward': reward.sum(),
                # 'avg_validation_cumulative_reward': avg_validation_cumulative_reward,
                'total_execution_cost': execution_cost.sum(),
                'total_waiting_cost': waiting_cost.sum(),
                'total_execution_time': execution_time.sum(),
                'total_waiting_time': waiting_time.sum(),
                'avg_waiting_time': waiting_time.mean(),
                'max_waiting_time': waiting_time.max(),
                'min_waiting_time': waiting_time.min(),
                'avg_waiting_cost': waiting_cost.mean(),
                'max_waiting_cost': waiting_cost.max(),
                'min_waiting_cost': waiting_cost.min(),
                'avg_execution_time': execution_time.mean(),
                'max_execution_time': execution_time.max(),
                'min_execution_time': execution_time.min(),
                'avg_execution_cost': execution_cost.mean(),
                'max_execution_cost': execution_cost.max(),
                'min_execution_cost': execution_cost.min(),
                'avg_reward': reward.mean(),
                'max_reward': reward.max(),
                'min_reward': reward.min(),
                'avg_full_time_get_action': full_time_get_action.mean(),
                'max_full_time_get_action': full_time_get_action.max(),
                'min_full_time_get_action': full_time_get_action.min(),
                'avg_full_agent_get_action_time': full_agent_get_action_time.mean(),
                'max_full_agent_get_action_time': full_agent_get_action_time.max(),
                'min_full_agent_get_action_time': full_agent_get_action_time.min(),
                'avg_agent_get_action_time': agent_get_action_time.mean(),
                'max_agent_get_action_time': agent_get_action_time.max(),
                'min_agent_get_action_time': agent_get_action_time.min()
            }
            return execution_stats
        except ValueError:
            pass

    def get_agent_name(self):
        agent_name = ''
        if self.agent_stats is not None and 'agent_type' in self.agent_stats and \
                self.agent_stats['agent_type'] is not None:
            agent_name = self.agent_stats['agent_type']
        return agent_name

    def get_agent_mode(self):
        mode = 'train'
        if self.agent_stats is not None and 'agent_parameters' in self.agent_stats:
            mode = self.agent_stats['agent_parameters']['mode']
        return mode

    def generate_filename(self, extension='json'):
        return 'stats_{}_task_executed={}_{}.{}' \
            .format(datetime.today().strftime('%Y-%m-%d_%H:%M'),
                    self.global_stats['task_to_generate'],
                    self.run_code,
                    extension)

    def to_dict(self):
        return {
            'run_code': self.run_code,
            'global_stats': self.global_stats,
            'agent_stats': self.agent_stats,
            'execution_history_stats': self.execution_history_stats
        }

    def db_stats(self):
        execution_stats = self.compute_execution_stats()
        stats = {
            'run_code': self.run_code,
            'task_generator_seed': self.global_stats['task_generator_seed'],
            'tasks_to_generate': self.global_stats['tasks_to_generate'],
            'tasks_to_bootstrap': self.global_stats['tasks_to_bootstrap'],
            'features_enabled': self.global_stats['features_enabled'],
            'task_succeeded': self.global_stats['task_succeeded'],
            'task_failed': self.global_stats['task_failed'],
            'validation_reward': self.global_stats['validation_reward'],
            'prepare_time': self.global_stats['prepare_time'],
            'start_execution_time': self.global_stats['start_execution_time'],
            'end_execution_time': self.global_stats['end_execution_time'],
            'end_time': self.global_stats['end_time'],
            'execution_run_time': self.global_stats['end_execution_time'] - self.global_stats['start_execution_time'],
            'full_run_time': self.global_stats['end_time'] - self.global_stats['prepare_time'],
        }
        for key, value in self.agent_stats.items():
            stats[key] = value
        for key, value in execution_stats.items():
            stats[key] = value
        return stats

    def to_json(self):
        return json.dumps(self.to_dict())

    @staticmethod
    def from_dict(stats_dict):
        stats = RunStats(run_code=stats_dict['run_code'])
        stats.set_global_stats(**stats_dict['global_stats'])
        stats.set_agent_stats(**stats_dict['agent_stats'])
        stats.set_execution_history_stats(**stats_dict['execution_history_stats'])
        stats = RunStats._assignments_history_post_load_from_dict(stats)
        return stats

    @staticmethod
    def _assignments_history_post_load_from_dict(stats):
        if 'assignments_history' in stats.execution_history_stats:
            assignments_history = stats.execution_history_stats['assignments_history']
            if assignments_history is not None and isinstance(assignments_history, list) \
                    and len(assignments_history) > 0 and isinstance(assignments_history[0], str):
                parsed = [json.loads(entry) for entry in assignments_history]
                parsed = sorted(parsed, key=lambda k: k['time_step'])
                stats.execution_history_stats['assignments_history'] = parsed
            return stats

    @staticmethod
    def from_json(json_stats):
        stats_dict = json.loads(json_stats)
        return RunStats.from_dict(stats_dict)

    @staticmethod
    def load_from_file(path):
        if os.path.exists(path):
            with open(path, 'rt') as file:
                stats_dict = json.load(file)
                return RunStats.from_dict(stats_dict)


class StatsBackend:

    def __init__(self, global_config: GlobalConfigHelper, logger=None, host=None):
        self.host = host
        self.global_config: GlobalConfigHelper = global_config
        self.logger = logger
        self.backend: BaseBackend = self._init_backend()
        self.stats_prefix = self.global_config.redis_statistics_prefix()

    def _init_backend(self):
        backend_class = get_backend_adapter(self.global_config.backend_adapter(), backed_type='base')
        return backend_class(config=self.global_config.backend_config(), logger=self.logger, host=self.host)

    def save_stats_group_property(self, stats_run_code: str, prop: str, value, as_list=False):
        full_key = f'{self.stats_prefix}_{stats_run_code}_{prop}'
        if as_list is True:
            values = value if isinstance(value, list) else [value]
            return self.backend.save_list(full_key, values)
        else:
            return self.backend.save(key=full_key, value=json.dumps(value, cls=NumpyEncoder))

    def save_stats_group(self, stats_run_code: str, group: dict, as_list=False):
        result = True
        for key, value in group.items():
            r = self.save_stats_group_property(stats_run_code, prop=key, value=value, as_list=as_list)
            if r is False:
                result = False
        return result

    def save(self, stats: RunStats):
        results = [self.save_stats_group(
            stats_run_code=stats.run_code,
            group=stats.global_stats
        ), self.save_stats_group(
            stats_run_code=stats.run_code,
            group=stats.agent_stats
        ), self.save_stats_group(
            stats_run_code=stats.run_code,
            group=stats.execution_history_stats,
            as_list=True
        )]
        for res in results:
            if res is False:
                return False
        return True

    def load_stats_group(self, run_code, group_keys, as_list=False):
        group = {}
        for key, _ in group_keys.items():
            full_key = f'{self.stats_prefix}_{run_code}_{key}'
            if as_list is True and key != 'selected_actions' and key != 'tasks_generated' \
                    and key != 'single_run_selected_actions':
                group[key] = self.backend.get_list(full_key)
            else:
                value = self.backend.get(full_key)
                if value is not None:
                    group[key] = json.loads(value)
                else:
                    group[key] = value
                    self.logger.warning(f'Value for key {key} is None')
        return group

    def load(self, run_code):
        stats = RunStats(run_code)
        global_stats = self.load_stats_group(run_code, stats.global_stats)
        agent_stats = self.load_stats_group(run_code, stats.agent_stats)
        execution_history_stats = self.load_stats_group(run_code, stats.execution_history_stats, as_list=True)
        stats.set_global_stats(**global_stats)
        stats.set_agent_stats(**agent_stats)
        stats.set_execution_history_stats(**execution_history_stats)
        return stats

    def delete_stats(self, run_code):
        pattern = f'{self.stats_prefix}_{run_code}_*'
        return self.backend.delete_all(pattern)
