import json

from flask import Flask
from flask_restful import Api
from werkzeug.exceptions import HTTPException

from rlq_scheduler.celery_app import app as celery_app
from rlq_scheduler.trajectory_collector.resources.health import HealthCheck
from rlq_scheduler.trajectory_collector.resources.trajectory import TrajectoryResource, TrajectoryListResource
from rlq_scheduler.trajectory_collector.system_consumer_callbacks import SYSTEM_CONSUMER_CALLBACKS
from rlq_scheduler.trajectory_collector.trajectory_collector_context import TrajectoryCollectorContext


def create_server(config_filename, global_config_filename):
    trajectory_collector_context = TrajectoryCollectorContext(
        config_filename=config_filename,
        global_config_filename=global_config_filename,
        celery_app=celery_app,
        system_consumer_callbacks=SYSTEM_CONSUMER_CALLBACKS
    )
    trajectory_collector_context.init()

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

    api.add_resource(TrajectoryListResource, '/api/trajectories', resource_class_kwargs={
        'context': trajectory_collector_context
    })
    api.add_resource(TrajectoryResource, '/api/trajectories/<trajectory_id>',
                     resource_class_kwargs={
                         'context': trajectory_collector_context
                     })
    api.add_resource(HealthCheck, '/api/health/check', resource_class_kwargs={
        'context': trajectory_collector_context
    })

    return app
