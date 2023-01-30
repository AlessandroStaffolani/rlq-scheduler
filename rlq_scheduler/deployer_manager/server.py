import json

from flask import Flask
from flask_restful import Api
from werkzeug.exceptions import HTTPException

from rlq_scheduler.common.config_helper import GlobalConfigHelper, DeployerManagerConfigHelper
from rlq_scheduler.common.utils.logger import get_logger
from rlq_scheduler.deployer_manager.deployer_manager import DeployerManager
from rlq_scheduler.deployer_manager.resources.deployer_manager import DMStatusResource, DMTriggerResource


def create_server(config_filename, global_config_filename):
    global_config = GlobalConfigHelper(config_path=global_config_filename)
    config = DeployerManagerConfigHelper(config_path=config_filename)
    logger = get_logger(config.logger())
    logger.info('Starting DeployerManager server')
    logger.info('ServiceBroker config are: {}'.format(global_config))
    logger.info('DeployerManager config are: {}'.format(config))
    deployer_manager: DeployerManager = DeployerManager(
        config=config,
        global_config=global_config,
        logger=logger
    )

    app = Flask(__name__)
    api = Api(app)

    @app.errorhandler(HTTPException)
    def handle_exception(e):
        """Return JSON instead of HTML for HTTP errors."""
        # start with the correct headers and status code from the error
        response = e.get_response()
        # replace the body with JSON
        response.data = json.dumps({
            "code": e.code,
            "name": e.name,
            "description": e.description,
        })
        response.content_type = "application/json"
        return response

    api.add_resource(DMStatusResource, '/api/system/status', resource_class_kwargs={
        'deployer_manager': deployer_manager,
        'logger': logger
    })

    api.add_resource(DMTriggerResource, '/api/system/trigger', resource_class_kwargs={
        'deployer_manager': deployer_manager,
        'logger': logger
    })

    return app
