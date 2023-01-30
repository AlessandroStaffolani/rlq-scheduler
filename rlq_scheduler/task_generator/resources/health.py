import json

from flask import Response
from flask_restful import Resource

from rlq_scheduler.common.system_status import ResourceStatus, is_resource_ok
from rlq_scheduler.task_generator.task_generator_context import TaskGeneratorContext


class HealthCheck(Resource):

    def __init__(self, context: TaskGeneratorContext):
        self.context: TaskGeneratorContext = context
        self.logger = context.logger

    def get(self):
        status = ResourceStatus.ERROR
        healthy_components = []
        unhealthy_components = []
        message = '{} is unhealthy'.format(self.context.name)
        if self.context.task_generator.is_ready:
            healthy_components.append({'component': 'task_generator'})
        else:
            unhealthy_components.append({'component': 'task_generator', 'message': 'TaskGenerator is not running'})

        if len(unhealthy_components) == 0 and is_resource_ok(self.context.status):
            status = self.context.status
            message = '{} is healthy'.format(self.context.name)
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
