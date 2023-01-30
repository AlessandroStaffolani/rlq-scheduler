import json
from logging import Logger

from flask import Response
from flask_restful import Resource

from rlq_scheduler.system_manager.system_manager_context import SystemManagerContext


class CeleryHealth(Resource):

    def __init__(self, context: SystemManagerContext):
        self.context = context
        self.logger: Logger = context.logger

    def get(self):
        health = self.context.celery_monitor.status()
        res = Response(
            response=json.dumps(health),
            status=200,
            headers=[("Content-Type", "application/json")]
        )
        return res
