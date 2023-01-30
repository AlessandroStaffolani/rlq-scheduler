import json
from logging import Logger

from flask import request, Response
from flask_restful import Resource, abort

from rlq_scheduler.common.trajectory import Trajectory, TrajectoryProperties
from rlq_scheduler.common.utils.encoders import NumpyEncoder
from rlq_scheduler.trajectory_collector.trajectory_collector_context import TrajectoryCollectorContext


class TrajectoryResource(Resource):
    def __init__(self, context: TrajectoryCollectorContext):
        self.context: TrajectoryCollectorContext = context
        self.logger: Logger = context.logger

    def get(self, trajectory_id):
        try:
            self.logger.info('Going to get the state', resource='TrajectoryCollectorResourceApi')
            trajectory: Trajectory = self.context.trajectory_backend.get_if_not_none_or_wait_update(
                trajectory_id,
                prop=TrajectoryProperties.STATE,
                max_retry=2,
                full_trajectory=True)
            res = Response(
                response=trajectory.to_json(),
                status=200,
                headers=[("Content-Type", "application/json")]
            )
            return res
        except Exception:
            res = Response(
                response={'message': 'TrajectoryCollector is not able to get the trajectory with id {}'
                    .format(trajectory_id)},
                status=400,
                headers=[("Content-Type", "application/json")]
            )
            return res

    def delete(self, trajectory_id):
        self.get_trajectory_if_exist(trajectory_id)
        self.context.trajectory_backend.delete(trajectory_id)
        res = Response(
            response=json.dumps({'message': f'Deleted as_dict with id {trajectory_id}'}),
            status=200,
            headers=[("Content-Type", "application/json")]
        )
        return res

    def put(self, trajectory_id):
        trajectory = self.get_trajectory_if_exist(trajectory_id)
        if trajectory is not None:
            req_body = request.get_json()
            if 'state' in req_body:
                trajectory.set_state(req_body['state'])
            if 'action' in req_body:
                trajectory.set_action(req_body['action'])
            if 'next_state' in req_body:
                trajectory.set_next_state(req_body['next_state'])
            if 'reward' in req_body:
                trajectory.set_reward(req_body['reward'])
            self.context.trajectory_backend.update(trajectory_id, trajectory)
            res = Response(
                response=trajectory.to_json(),
                status=200,
                headers=[("Content-Type", "application/json")]
            )
            return res

    def get_trajectory_if_exist(self, trajectory_id) -> Trajectory or None:
        trajectory = self.context.trajectory_backend.get(trajectory_id)
        if trajectory is None:
            abort(404, message="Trajectory {} doesn't exist".format(trajectory_id))
            return None
        else:
            return trajectory


class TrajectoryListResource(Resource):
    def __init__(self, context: TrajectoryCollectorContext):
        self.context: TrajectoryCollectorContext = context
        self.logger: Logger = context.logger

    def get(self):
        trajectories = self.context.backend.get_all()
        req_body = request.get_json()
        if req_body is not None and 'ordered' in req_body and req_body['ordered'] is True:
            trajectories = sorted(trajectories, key=lambda x: x[TrajectoryProperties.CREATED_AT])
        trajectories_to_return = [t.as_dict(data_formated=True, keys_as_string=True) for t in trajectories]
        res = Response(
            response=json.dumps(trajectories_to_return, cls=NumpyEncoder),
            status=200,
            headers=[("Content-Type", "application/json")]
        )
        return res
