from logging import Logger
from multiprocessing.pool import ThreadPool
from copy import deepcopy

from bson import ObjectId

from rlq_scheduler.common.backends.backend_factory import get_backend_adapter
from rlq_scheduler.common.backends.base_backend import BaseTrajectoryBackend
from rlq_scheduler.common.config_helper import GlobalConfigHelper
from rlq_scheduler.common.trajectory import Trajectory
from rlq_scheduler.common.trajectory_saver.database import Database

RUNS_INFO = 'runs_info'
TRAJECTORIES = 'trajectories'


class Saver:

    def __init__(self, global_config: GlobalConfigHelper, logger: Logger):
        self.logger: Logger = logger
        self.global_config: GlobalConfigHelper = global_config
        backend_class = get_backend_adapter(self.global_config.backend_adapter(), backed_type='trajectory')
        self.trajectory_backend: BaseTrajectoryBackend = backend_class(
            config=self.global_config.backend_config(),
            logger=self.logger)
        self.db: Database = Database(global_config=self.global_config, logger=logger)
        self.trajectory_buffer = []
        self.trajectory_extra_buffer = {}
        self.current_run_code = None
        self.async_pool = ThreadPool(processes=2)
        self.disabled = False

    def init(self):
        initialized = self.db.init()
        if initialized:
            self.logger.info('Trajectory Saver initialized with success and connected to the Database')
        else:
            self.disabled = True
        return initialized

    def push_trajectory(self, trajectory_id: str):
        if not self.disabled:
            self.trajectory_buffer.append(trajectory_id)
            self.logger.debug('Added to trajectory_id buffer trajectory with id: {}. Current buffer length is {}'
                              .format(trajectory_id, len(self.trajectory_buffer)))
            if len(self.trajectory_buffer) == self.global_config.saver_save_interval():
                self.async_pool.apply_async(self.save_bulk_trajectories,
                                            args=(deepcopy(self.trajectory_buffer), ),
                                            error_callback=lambda e: self.logger.exception(e))
                self.trajectory_buffer = []
                self.logger.info('Trajectory buffer reached save interval size ({}) started trajectory saving'
                                 .format(self.global_config.saver_save_interval()))

    def push_trajectory_extra(self, field, trajectory_id, value):
        if not self.disabled:
            if field in self.trajectory_extra_buffer:
                buffer = self.trajectory_extra_buffer[field]
            else:
                buffer = self.trajectory_extra_buffer[field] = {}
            buffer[trajectory_id] = value
            self.logger.debug('Added to trajectory extra buffer field: {} for trajectory with id: {}.'
                              ' Current {} buffer length is {}'
                              .format(field, trajectory_id, field, len(buffer)))
            if len(buffer) == self.global_config.saver_save_interval():
                self.async_pool.apply_async(self.save_bulk_trajectories_extra,
                                            args=(deepcopy(buffer), field),
                                            error_callback=lambda e: self.logger.exception(e))
                self.trajectory_extra_buffer[field] = {}
                self.logger.info('{} buffer reached save interval size ({}) started saving'
                                 .format(field, self.global_config.saver_save_interval()))

    def save_bulk_trajectories(self, trajectories_ids: list):
        if not self.disabled:
            documents = []
            for t_id in trajectories_ids:
                trajectory: Trajectory = self.trajectory_backend.get(trajectory_id=t_id)
                trajectory: dict = trajectory.to_plain_dict()
                trajectory['run_code'] = self.current_run_code
                documents.append(deepcopy(trajectory))
            self.db.bulk_update(TRAJECTORIES, documents, query_param='id', upsert=True)
            self.logger.info('{} trajectories have been saved'.format(len(documents)))
            update = {'$push': {'trajectories': {'$each': trajectories_ids}}}
            self.db.update(
                collection=RUNS_INFO,
                query={'run_code': self.current_run_code},
                update_obj=update
            )
            self.logger.info('Added {} trajectories ids to {} with run_code: {}'
                             .format(len(trajectories_ids), RUNS_INFO, self.current_run_code))

    def save_bulk_trajectories_extra(self, buffer: dict, field: str):
        if not self.disabled:
            documents = []
            for t_id, value in buffer.items():
                documents.append({
                    'id': t_id,
                    field: value
                })
            self.db.bulk_update(TRAJECTORIES, documents, query_param='id', upsert=True)
            self.logger.info('{} trajectories {} values have been saved'.format(len(documents), field))

    def flush(self):
        if not self.disabled:
            self._flush_trajectories()
            self._flush_trajectories_extras()

    def _flush_trajectories(self):
        if len(self.trajectory_buffer) > 0:
            self.save_bulk_trajectories(self.trajectory_buffer)
            self.logger.info('Trajectory buffer flushed with ({}) trajectories'
                             .format(len(self.trajectory_buffer)))
            self.trajectory_buffer = []

    def _flush_trajectories_extras(self):
        documents = []
        for field, buffer in self.trajectory_extra_buffer.items():
            for t_id, value in buffer.items():
                documents.append({
                    'id': t_id,
                    field: value
                })
        if len(documents) > 0:
            self.db.bulk_update(TRAJECTORIES, documents, query_param='id', upsert=True)
            self.trajectory_extra_buffer = {}
            self.logger.info('{} extra information flushed'
                             .format(len(documents)))

    def save_run_info(self, run_code,
                      tasks_to_generate=None,
                      features_enabled=None,
                      agent_parameters=None,
                      agent_name=None,
                      tasks_config=None,
                      workers_config=None,
                      run_functions=None,
                      state_features=None,
                      context_features=None,
                      agent_config=None,
                      **kwargs
                      ):
        try:
            if not self.disabled:
                update_obj = {}
                if tasks_to_generate is not None:
                    update_obj['tasks_to_generate'] = tasks_to_generate
                if features_enabled is not None:
                    update_obj['features_enabled'] = features_enabled
                if agent_name is not None:
                    update_obj['agent_name'] = agent_name
                if agent_parameters is not None:
                    update_obj['agent_parameters'] = agent_parameters
                if tasks_config is not None:
                    update_obj['tasks_config'] = tasks_config
                if workers_config is not None:
                    update_obj['workers_config'] = workers_config
                if run_functions is not None:
                    update_obj['run_functions'] = run_functions
                if state_features is not None:
                    update_obj['state_features'] = state_features
                if context_features is not None:
                    update_obj['context_features'] = context_features
                if agent_config is not None:
                    update_obj['agent_config'] = agent_config
                if len(kwargs) > 0:
                    for param_name, param_value in kwargs.items():
                        update_obj[param_name] = param_value
                if len(update_obj) == 0:
                    update_obj = {
                        'tasks_to_generate': None,
                        'features_enabled': None,
                        'agent_name': None,
                        'agent_parameters': None,
                        'trajectories': [],
                        'tasks_config': None,
                        'workers_config': None,
                        'run_functions': None,
                        'state_features': None,
                        'context_features': None,
                        'agent_config': None
                    }
                self.db.update(
                    collection=RUNS_INFO,
                    query={'run_code': run_code},
                    update_obj={'$set': update_obj},
                    upsert=True
                )
                self.logger.info('Updated {} for run with code: {}.'.format(RUNS_INFO, run_code))
                if self.current_run_code is None:
                    self.current_run_code = run_code
        except Exception as e:
            self.logger.exception(e)

    def _add_trajectory_to_run_info(self, run_code, trajectory_object_id: ObjectId or str):
        update = {'$push': {'trajectories': trajectory_object_id}}
        self.db.update(
            collection=RUNS_INFO,
            query={'run_code': run_code},
            update_obj=update
        )
        self.logger.info('Added trajectory id {} to {} with run_code: {}'
                         .format(trajectory_object_id, RUNS_INFO, run_code))

    def save_trajectory(self, run_code, trajectory: Trajectory):
        try:
            if not self.disabled:
                document = trajectory.to_plain_dict()
                document['run_code'] = run_code
                # document['trajectory_info'] = {}
                # document['execution_info'] = {}
                t_result = self.db.update(
                    collection=TRAJECTORIES,
                    query={'id': trajectory.id()},
                    update_obj={'$set': trajectory.to_plain_dict()},
                    upsert=True
                    )
                self.logger.info('Trajectory with id: {} saved with object_id: {}'
                                 .format(trajectory.id(), t_result['_id']))
                self._add_trajectory_to_run_info(run_code, t_result['_id'])
        except Exception as e:
            self.logger.exception(e)

    def add_info_to_trajectory(self, trajectory_id, field, value):
        try:
            if not self.disabled:
                self.db.update(
                    collection=TRAJECTORIES,
                    query={'id': trajectory_id},
                    update_obj={'$set': {field: value}},
                    upsert=True
                )
                self.logger.info('{} updated for trajectory with id: {}'.format(field, trajectory_id))
        except Exception as e:
            self.logger.exception(e)

    def stop(self):
        self.async_pool.close()
        self.async_pool.join()
        self.trajectory_backend.close()
