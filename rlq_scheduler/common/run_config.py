import json
from copy import deepcopy
from uuid import uuid4
from datetime import datetime

from rlq_scheduler.common.config_helper import RunConfigHelper, BaseConfigHelper


class RunConfigEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, RunConfig):
            return obj.to_dict()
        elif isinstance(obj, BaseConfigHelper):
            return obj.config
        else:
            return super(RunConfigEncoder, self).default(obj)


def generate_run_name(run_code, task_executed, start_time, extension=None):
    filename = '{}_started_at={}_task-scheduled={}'\
        .format(run_code, datetime.fromtimestamp(start_time).strftime('%Y-%m-%d_%H:%M:%S'), task_executed)
    if extension is None:
        return filename
    else:
        return f'{filename}.{extension}'


class RunConfig:

    def __init__(self,
                 run_config,
                 run_code=None):
        self.run_code = str(uuid4()) if run_code is None else run_code
        self.config: RunConfigHelper = RunConfigHelper(config=deepcopy(run_config))

    def to_dict(self):
        return {
            'run_code': self.run_code,
            'config': self.config.config
        }

    def minimal_props(self):
        agent_type_name = self.config['global']['features_enabled']['agent_type']['name']
        policy_name = self.config['global']['features_enabled']['agent_type']['policy']
        props = {
            'run_code': self.run_code,
            'seeds': {
                'task_generator': self.config['task_generator']['random_seed'],
                'agent': self.config['agent']['global']['random_seed']
            },
            'agent_type': self.config['global']['features_enabled']['agent_type'],
            'active_agent_parameters': self.config['agent']['agents_parameters'][agent_type_name],
            'active_policy_parameters': self.config['agent']['policies_parameters'][policy_name] if policy_name is not None else None,
            'tasks_to_generate': self.config['task_generator']['tasks_to_generate'],
            'global_features_enabled': {
                'waiting_time': self.config['global']['features_enabled']['waiting_time'],
                'expandable_pool': self.config['global']['features_enabled']['expandable_pool']
            },
            'state_features': self.config['global']['state']['features']
        }
        return props

    def to_json(self):
        return json.dumps(self.to_dict())

    def __str__(self):
        return '<RunConfig minimal_info={} >'.format(self.minimal_props())

    @staticmethod
    def from_dict(rc_dict):
        return RunConfig(
            run_config=RunConfigHelper(config=rc_dict['config']),
            run_code=rc_dict['run_code']
        )

    @staticmethod
    def from_json(json_string):
        rc_dict = json.loads(json_string)
        return RunConfig.from_dict(rc_dict)
