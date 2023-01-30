import json

from flask import Flask
from flask_restful import Api
from werkzeug.exceptions import HTTPException

from rlq_scheduler.task_generator.resources.health import HealthCheck
from rlq_scheduler.task_generator.system_consumer_callbacks import SYSTEM_CONSUMER_CALLBACKS
from rlq_scheduler.task_generator.task_generator_context import TaskGeneratorContext


def create_server(config_filename, global_config_filename):
    task_generator_context = TaskGeneratorContext(
        config_filename=config_filename,
        global_config_filename=global_config_filename,
        system_consumer_callbacks=SYSTEM_CONSUMER_CALLBACKS
    )

    task_generator_context.init()

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

    api.add_resource(HealthCheck, '/api/health/check', resource_class_kwargs={
        'context': task_generator_context
    })

    return app
