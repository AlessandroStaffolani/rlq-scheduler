import json
from copy import deepcopy

from flask import Response
from flask_restful import Resource

from rlq_scheduler.system_manager.system_manager_context import SystemManagerContext
from rlq_scheduler.common.system_status import SystemStatus


class SystemStatusResource(Resource):

    def __init__(self, context: SystemManagerContext):
        self.context = context
        self.logger = context.logger

    def get(self):
        resources_status = deepcopy(self.context.system_manager.resources_status)
        resources_status['celery'] = self.context.system_manager.celery_status
        system_status = self.context.system_manager.system_status
        message = ''

        if system_status == SystemStatus.NOT_READY:
            message = 'System resources are not ready yet, waiting for the initialization'
        elif system_status == SystemStatus.WAITING:
            message = 'System is waiting for a new run to be scheduled'
        elif system_status == SystemStatus.READY:
            message = 'System is ready to start the new run'
        elif system_status == SystemStatus.RUNNING:
            message = 'System is running a run'
        elif system_status == SystemStatus.STOPPED:
            message = 'System is stopped'
        elif system_status == SystemStatus.ERROR:
            message = 'System is in a blocking error. It is required a manual intervention'

        executed_runs = len(self.context.run_manager.executed_runs)
        runs_to_execute = len(self.context.run_manager.runs_config_to_execute) + executed_runs
        current_run_status = None
        if self.context.current_run_code is not None and self.context.current_run_config is not None:
            runs_to_execute += 1
            current_run_status = {
                'run_code': self.context.current_run_code,
                'tasks_to_execute': self.context.current_run_config.tasks_to_generate_total_number(),
                'tasks_executed': self.context.run_manager.current_tasks_executed,
                'agent': self.context.current_run_config.agent_full_name(),
                'reward_function': self.context.current_run_config.reward_function(),
                'tasks_generation_config': self.context.current_run_config.tasks_to_generate()
            }

        res = Response(
            response=json.dumps({
                'status': system_status,
                'message': message,
                'phase': self.context.current_phase,
                'resources_status': resources_status,
                'runs': {
                    'runs_to_execute': runs_to_execute,
                    'executed_runs': executed_runs
                },
                'current_run_status': current_run_status,
            }),
            status=200,
            headers=[("Content-Type", "application/json")]
        )
        return res
