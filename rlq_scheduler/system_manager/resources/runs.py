import json
from copy import deepcopy

import numpy as np

from flask import Response, request
from flask_restful import Resource

from rlq_scheduler.common.config_helper import MultiRunConfigHelper, RunConfigHelper
from rlq_scheduler.common.run_config import RunConfigEncoder, RunConfig
from rlq_scheduler.common.run_config_generator import prepare_runs_random_seeds, prepare_runs_config
from rlq_scheduler.system_manager.system_manager_context import SystemManagerContext


class ControlRunResources(Resource):

    def __init__(self, context: SystemManagerContext):
        self.context = context
        self.logger = context.logger

    def post(self):
        status = 400
        message = ''
        run_config = None
        req_body = request.get_json()
        if 'next_run' in req_body and 'auto_run' in req_body:
            next_run = req_body['next_run']
            auto_run = req_body['auto_run']
            if isinstance(next_run, bool) and isinstance(auto_run, bool):
                self.context.run_manager.is_auto_run = auto_run
                if next_run is True:
                    is_run_scheduled: bool = self.context.run_manager.schedule_next_run()
                    if is_run_scheduled is True:
                        status = 200
                        message = 'Run with code {} have been scheduled' \
                            .format(self.context.run_manager.current_run.run_code)
                        run_config = self.context.run_manager.current_run.config.config
                    else:
                        status = 400
                        message = 'No run has been scheduled. System may not be in WAITING status ' \
                                  'or no more run are available'
                else:
                    status = 200
                    message = 'Run Manager set auto_run to {}'.format(auto_run)
            else:
                status = 400
                message = 'Both next_run and auto_run must be boolean'
        else:
            status = 400
            message = 'Request body bad formatted. It must contain next_run and auto_run'
        return Response(
            response=json.dumps({
                'status': status,
                'message': message,
                'run_config': run_config
            }),
            status=status,
            headers=[("Content-Type", "application/json")]
        )


class CurrentRunResource(Resource):

    def __init__(self, context: SystemManagerContext):
        self.context = context
        self.logger = context.logger

    def get(self):
        current_run = deepcopy(self.context.run_manager.current_run.to_dict())
        try:
            if current_run['global']['features_enabled']['evaluation'] \
                    and current_run['task_generator']['tasks_to_generate'][0]['tasks_to_generate']:
                with open(self.context.global_config.datasets_google_traces_eval_dataset_path(), 'r') as f:
                    dataset = json.load(f)
                    current_run['task_generator']['tasks_to_generate'][0]['tasks_to_generate'] = len(dataset)
        except Exception:
            pass
        return Response(
            response=json.dumps({
                'run_under_execution': current_run,
                'runs_to_execute_count': len(self.context.run_manager.runs_config_to_execute),
                'runs_executed': len(self.context.run_manager.executed_runs)
            }, cls=RunConfigEncoder),
            status=200,
            headers=[("Content-Type", "application/json")]
        )


class RunsResource(Resource):

    def __init__(self, context: SystemManagerContext):
        self.context = context
        self.logger = context.logger

    def get(self):
        args = request.args.to_dict()
        if 'populate' in args and args['populate'] == 'true':
            executed_runs = self.context.run_manager.executed_runs
        else:
            executed_runs = len(self.context.run_manager.executed_runs)
        return Response(
            response=json.dumps({
                'run_under_execution': self.context.run_manager.current_run,
                'runs_to_execute_count': len(self.context.run_manager.runs_config_to_execute),
                'executed_runs': executed_runs,
                'runs_to_execute_config': self.context.run_manager.runs_config_to_execute
            }, cls=RunConfigEncoder),
            status=200,
            headers=[("Content-Type", "application/json")]
        )

    def post(self):
        req_body = request.get_json()
        status = 200
        message = ''
        if 'generation_mode' in req_body:
            generation_mode = req_body['generation_mode']
            config_file = None
            config = None
            if 'config_file' in req_body:
                config_file = req_body['config_file']
            if 'config' in req_body:
                config = req_body['config']
            if config is None and config_file is None:
                status = 400
                message = 'one between config_file and config property is mandatory'
            else:
                if generation_mode == 'multi':
                    if config_file is not None:
                        runs = self._create_runs_configs(config_file)
                    else:
                        runs = self._create_runs_configs(config_file=None, config=config)
                    if runs is not None:
                        self.context.run_manager.add_run_to_execute(runs)
                        message = 'Scheduled {} new runs. Now total number is {}' \
                            .format(len(runs), len(self.context.run_manager.runs_config_to_execute))
                    else:
                        status = 400
                        message = "Error creating multi run config"
                elif generation_mode == 'single':
                    replace = req_body['replace']
                    if config_file is not None:
                        run_config = self._prepare_run_config(config_file)
                    else:
                        run_config = self._prepare_run_config(config_file=None, config=config)
                    if run_config is not None:
                        if replace is not None and replace is True:
                            run_config.config.save_to_file(filepath='config', filename='run_config')

                        self.context.run_manager.add_run_to_execute(run_config)
                        message = 'Scheduled new run. Now total number is {}' \
                            .format(len(self.context.run_manager.runs_config_to_execute))
                    else:
                        status = 400
                        message = "Error creating single run config"
                else:
                    status = 400
                    message = 'If generation_mode == "multi" config_file is required, ' \
                              'else if generation_mode == "single" config_folder is required'
        else:
            status = 400
            message = 'generation_mode field missing'

        return Response(
            response=json.dumps({
                'status': status,
                'message': message
            }),
            status=status,
            headers=[("Content-Type", "application/json")]
        )

    def delete(self):
        self.context.run_manager.runs_config_to_execute = []
        return Response(
            response=json.dumps({
                'message': 'All the runs config scheduled have been removed'
            }, cls=RunConfigEncoder),
            status=200,
            headers=[("Content-Type", "application/json")]
        )

    def _create_runs_configs(self, config_file=None, config=None):
        multi_config = None
        if config_file is not None:
            multi_config = MultiRunConfigHelper(config_path=config_file)
        elif config is not None:
            multi_config = MultiRunConfigHelper(config=config)
        if multi_config is not None:
            random = np.random.RandomState(multi_config.global_seed())
            seeds = prepare_runs_random_seeds(random, multi_run_config=multi_config)
            return prepare_runs_config(seeds, multi_config, self.context.run_manager.config_folder)
        else:
            return None

    def _prepare_run_config(self, config_file=None, config=None) -> RunConfigHelper or None:
        if config_file is not None:
            return RunConfig(run_config=RunConfigHelper(config_path=config_file).config)
        elif config is not None:
            return RunConfig(run_config=RunConfigHelper(config=config).config)
        else:
            return None
