import json

from flask import Response
from flask_restful import Resource

from rlq_scheduler.common.system_status import ResourceStatus, is_resource_ok
from rlq_scheduler.trajectory_collector.trajectory_collector_context import TrajectoryCollectorContext


class HealthCheck(Resource):

    def __init__(self, context: TrajectoryCollectorContext):
        self.context: TrajectoryCollectorContext = context
        self.logger = context.logger

    def get(self):
        status = ResourceStatus.ERROR
        healthy_components = []
        unhealthy_components = []
        message = '{} is unhealthy'.format(self.context.name)
        if self.context.consumer.is_alive() and self.context.consumer.is_ready:
            healthy_components.append({'component': 'consumer'})
        else:
            healthy_components.append({'component': 'consumer', 'message': 'Consumer thread is not running'})
        if self.context.trajectory_builder.is_ready:
            healthy_components.append({'component': 'trajectory_builder'})
        else:
            healthy_components.append({'component': 'trajectory_builder',
                                       'message': 'TrajectoryBuilder is not running'})
        if self.context.workers_state_builder.is_running:
            healthy_components.append({'component': 'workers_state_builder'})
        else:
            healthy_components.append({'component': 'workers_state_builder',
                                       'message': 'WorkersStateBuilder is not running'})

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
