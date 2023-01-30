import json
from logging import Logger

from flask import Response, request
from flask_restful import Resource

from rlq_scheduler.deployer_manager.common import DeploymentStatus
from rlq_scheduler.deployer_manager.deployer_manager import DeployerManager


class DMStatusResource(Resource):

    def __init__(self,
                 deployer_manager: DeployerManager,
                 logger: Logger):
        self.deployer_manager: DeployerManager = deployer_manager
        self.logger: Logger = logger

    def get(self):
        status = self.deployer_manager.system_status()
        status['status'] = status['status'].name
        res = Response(
            response=json.dumps(status),
            status=200,
            headers=[("Content-Type", "application/json")]
        )
        return res


class DMTriggerResource(Resource):

    def __init__(self,
                 deployer_manager: DeployerManager,
                 logger: Logger):
        self.deployer_manager: DeployerManager = deployer_manager
        self.logger: Logger = logger

    def post(self):
        status = 500
        message = ''
        current_status = self.deployer_manager.status
        req_body = request.get_json()
        if req_body is not None and 'action' in req_body:
            action = req_body['action']
            if action == 'deploy':
                if current_status != DeploymentStatus.CLEANING and current_status != DeploymentStatus.DEPLOYING:
                    self.deployer_manager.deploy()
                    status = 200
                    message = 'DeployerManager started to deploy the system in background, ' \
                              'check the log or perform the status request'
                else:
                    status = 400
                    message = 'trying to deploy the system while in {} status is forbidden'.format(current_status)
            elif action == 'cleanup':
                if self.deployer_manager.status == DeploymentStatus.READY:
                    self.deployer_manager.clean_up()
                    status = 200
                    message = 'DeployerManager started to clean up the system in background, ' \
                              'check the log or perform the status request'
                else:
                    status = 400
                    message = 'trying to clean up a system not deployed already'
            else:
                status = 400
                message = 'action provided is not valid. Use one of "deploy" or "cleanup"'
        else:
            status = 400
            message = 'request body must provide an action'
        res = Response(
            response=json.dumps({'message': message}),
            status=status,
            headers=[("Content-Type", "application/json")]
        )
        return res
