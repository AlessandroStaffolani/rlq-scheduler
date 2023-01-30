import json

from flask import Response
from flask_restful import Resource

from rlq_scheduler.common.system_status import ResourceStatus, is_resource_ok
from rlq_scheduler.system_manager.system_manager_context import SystemManagerContext


class HealthCheck(Resource):

    def __init__(self, context: SystemManagerContext):
        self.context = context
        self.logger = context.logger

    def get(self):
        status = ResourceStatus.ERROR
        healthy_components = []
        unhealthy_components = []
        message = 'SystemManager is unhealthy'
        if self.context.system_manager.is_running is True:
            healthy_components.append({'component': 'system_manager'})
        else:
            unhealthy_components.append({'component': 'system_manager', 'message': 'SystemManager is not running'})
            
        if self.context.run_manager.is_running is True:
            healthy_components.append({'component': 'run_manager'})
        else:
            unhealthy_components.append({'component': 'run_manager', 'message': 'RunManager is not running'})

        if len(unhealthy_components) == 0 and is_resource_ok(self.context.status):
            status = self.context.status
            message = 'SystemManager is healthy'
        agent_health = {
            'status': status,
            'message': message,
            'healthy_components': healthy_components,
            'unhealthy_components': unhealthy_components
        }
        res = Response(
            response=json.dumps(agent_health),
            status=200,
            headers=[("Content-Type", "application/json")]
        )
        return res
