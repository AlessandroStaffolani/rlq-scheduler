import json

from flask import Response
from flask_restful import Resource

from rlq_scheduler.agent.agent_context import AgentContext
from rlq_scheduler.common.system_status import ResourceStatus, is_resource_ok


class HealthCheck(Resource):

    def __init__(self, context: AgentContext):
        self.context = context
        self.logger = context.logger

    def get(self):
        status = ResourceStatus.ERROR
        healthy_components = []
        unhealthy_components = []
        message = '{} is unhealthy'.format(self.context.name)
        if status == ResourceStatus.READY or status == ResourceStatus.RUNNING:
            if self.context.agent is not None:
                healthy_components.append({'component': 'agent'})
            else:
                unhealthy_components.append({'component': 'agent', 'message': 'Agent has not been initialized'})

            if len(unhealthy_components) == 0 and is_resource_ok(self.context.status):
                status = self.context.status
                message = '{} is healthy'.format(self.context.name)
        else:
            if is_resource_ok(self.context.status):
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
