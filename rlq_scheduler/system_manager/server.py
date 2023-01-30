import json
import time

from flask import Flask
from flask_restful import Api
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from rlq_scheduler.celery_app import app as celery_app
from rlq_scheduler.system_manager.resources.runs import CurrentRunResource, RunsResource, ControlRunResources
from rlq_scheduler.system_manager.resources.system import SystemStatusResource
from rlq_scheduler.system_manager.system_consumer_callbacks import SYSTEM_CONSUMER_CALLBACKS
from rlq_scheduler.system_manager.system_manager_context import SystemManagerContext


def create_server(config_filename,
                  multi_run_config_filename,
                  global_config_filename):
    system_manager_context: SystemManagerContext = SystemManagerContext(
        config_filename=config_filename,
        multi_run_config_filename=multi_run_config_filename,
        global_config_filename=global_config_filename,
        celery_app=celery_app,
        system_consumer_callbacks=SYSTEM_CONSUMER_CALLBACKS
    )

    time.sleep(1)

    system_manager_context.init()

    app = Flask(__name__)
    api = Api(app)
    CORS(app)

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

    # STATUS ENDPOINTS #

    api.add_resource(SystemStatusResource, '/api/system/status', resource_class_kwargs={
        'context': system_manager_context
    })

    # RUNS ENDPOINTS #

    api.add_resource(CurrentRunResource, '/api/runs/current', resource_class_kwargs={
        'context': system_manager_context
    })

    api.add_resource(ControlRunResources, '/api/runs/control', resource_class_kwargs={
        'context': system_manager_context
    })

    api.add_resource(RunsResource, '/api/runs', resource_class_kwargs={
        'context': system_manager_context
    })

    return app
