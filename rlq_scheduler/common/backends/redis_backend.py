import json

import redis

from rlq_scheduler.common.backends.base_backend import BaseTrajectoryBackend, BaseBackend, BaseBufferBackend
from rlq_scheduler.common.distributed_queue.redis_queue import RedisQueue
from rlq_scheduler.common.exceptions import NoStateFoundForTrajectoryException
from rlq_scheduler.common.redis_connection import RedisConnectionFactory
from rlq_scheduler.common.trajectory import Trajectory, TrajectoryProperties
from rlq_scheduler.common.utils.decorators import retry_on_exceptions
from rlq_scheduler.common.utils.encoders import NumpyEncoder


class RedisBackend(BaseBackend):

    def __init__(self, config=None, logger=None, host=None):
        super(RedisBackend, self).__init__(config=config, logger=logger)
        if host is not None:
            self.config['connection']['host'] = host
        # self.redis_connection_factory = RedisConnectionFactory(self.config['connection'])
        self.redis_connection: redis.Redis = redis.Redis(
            host=self.config['connection']['host'],
            port=self.config['connection']['port'],
            db=self.config['connection']['db']
        )

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def save(self, key: str, value):
        try:
            result = self.redis_connection.set(key, value.encode('utf-8'))
            if result:
                self.logger.debug('New item for key {} has been saved'.format(key), resource='RedisBackend')
                return True
            else:
                self.logger.warning(result, resource='RedisBackend')
                return False
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return False

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def save_list(self, key: str, values: list):
        try:
            result = self.redis_connection.rpush(key, *values)
            if result == len(values):
                self.logger.debug('New item for key {} has been saved'.format(key), resource='RedisBackend')
                return True
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return False

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def update(self, key: str, value):
        return self.save(key, value)

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def append_to_list(self, key: str, values):
        return self.save_list(key, values)

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def get(self, key):
        try:
            value = self.redis_connection.get(key)
            if value is not None:
                result = value.decode('utf-8')
                return result
            else:
                return None
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def get_list(self, key: str):
        try:
            values = self.redis_connection.lrange(key, 0, -1)
            if len(values) > 0:
                result = [v.decode('utf-8') for v in values]
                return result
            else:
                return None
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def get_all(self, key_pattern=None) -> list or None:
        try:
            pattern = key_pattern if key_pattern is not None else '*'
            keys = self.redis_connection.keys(pattern)
            results_str = self.redis_connection.mget(keys)
            results_str = [i.decode('utf-8') for i in results_str]
            return results_str
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError,))
    def get_keys(self, key_pattern=None):
        try:
            pattern = key_pattern if key_pattern is not None else '*'
            keys = self.redis_connection.keys(pattern)
            results_str = [i.decode('utf-8') for i in keys]
            return results_str
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def delete(self, key) -> int or None:
        try:
            return self.redis_connection.delete(key)
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def delete_all(self, pattern):
        try:
            return self.redis_connection.delete(*self.redis_connection.keys(pattern))
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def check_connection(self):
        try:
            return self.redis_connection.ping()
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return e

    def close(self):
        self.redis_connection.close()
        self.redis_connection.client().close()
        self.redis_connection.client().connection_pool.disconnect()


class RedisTrajectoryBackend(BaseTrajectoryBackend):

    def __init__(self, config=None, logger=None, host=None):
        super(RedisTrajectoryBackend, self).__init__(config=config, logger=logger)
        if host is not None:
            self.config['connection']['host'] = host
        self.redis_connection_factory = RedisConnectionFactory(self.config['connection'])
        self.redis_connection: redis.Redis = self.redis_connection_factory.get_connection()
        self.redis_db = self.config['connection']['db']
        self.queue = RedisQueue(config, logger)
        self.logger.info('Init redis backend adapter', resource='RedisBackend')

    def _set(self, key, value, use_setnx=False):
        try:
            if use_setnx is True:
                result = self.redis_connection.setnx(key, value.encode('utf-8'))
            else:
                result = self.redis_connection.set(key, value.encode('utf-8'))
            if result:
                return True
            else:
                self.logger.warning(result, resource='RedisBackend')
                return False
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return False

    def _save(self, trajectory_id, trajectory: Trajectory, use_setnx=False) -> bool:
        base_key = self.compone_key(trajectory_id)
        result = True
        for prop, value in trajectory.items():
            key = f'{base_key}_{prop.value}'
            json_value = json.dumps(value, cls=NumpyEncoder)
            if not self._set(key, json_value, use_setnx=use_setnx):
                result = False
                self.logger.warning('Failed to save property: {} for trajectory with id: {}'
                                    .format(prop, trajectory_id), resource='RedisBackend')
        if result is True:
            self.logger.debug('Trajectory with id: {} saved on base_key: {}'.format(trajectory_id, base_key),
                              resource='RedisBackend')
        else:
            self.logger.warning('Failed to save trajectory properties with id: {} and base_key: {}'
                                .format(trajectory_id, base_key), resource='RedisBackend')
        return result

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def save(self, trajectory_id: str, trajectory: Trajectory, use_setnx=False) -> bool:
        return self._save(trajectory_id=trajectory.id(), trajectory=trajectory, use_setnx=use_setnx)

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def save_property(self, trajectory_id: str, value, prop: TrajectoryProperties, compone_key=True):
        if compone_key is True:
            base_key = self.compone_key(trajectory_id)
        else:
            base_key = trajectory_id
        json_value = json.dumps(value, cls=NumpyEncoder)
        return self._set(key=f'{base_key}_{prop.value}', value=json_value)

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def set_task_waiting_time(self, task_id: str, started, waited=None):
        key = self.task_waiting_time_prefix + '_' + task_id
        waiting_struct = {
            'started': started,
            'waited': waited if waited is not None else None
        }
        return self._set(key, json.dumps(waiting_struct))

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def update(self, trajectory_id: str, trajectory: Trajectory) -> bool:
        return self._save(trajectory_id=trajectory_id, trajectory=trajectory)

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def update_property(self, trajectory_id: str, value, prop: TrajectoryProperties, compone_key=True):
        if compone_key is True:
            base_key = self.compone_key(trajectory_id)
        else:
            base_key = trajectory_id
        json_value = json.dumps(value, cls=NumpyEncoder)
        return self._set(key=f'{base_key}_{prop.value}', value=json_value)

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def compone_key(self, trajectory_id):
        return self.trajectory_prefix + '_' + trajectory_id

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def get(self, trajectory_id: str, compone_key=True):
        if compone_key is True:
            base_key = self.trajectory_prefix + '_' + trajectory_id
        else:
            base_key = trajectory_id
        properties = Trajectory.get_trajectory_properties()
        keys = [f'{base_key}_{prop}' for prop in properties]
        try:
            trajectory_values = self.redis_connection.mget(keys)
            none_values = 0
            for v in trajectory_values:
                if v is None:
                    none_values += 1
            if none_values == len(trajectory_values):
                # No trajectory found
                return None
            else:
                # Trajectory exists, create is and return it
                t_id = base_key.split('_')[1]
                trajectory = Trajectory(id=t_id)
                for i, k in enumerate(keys):
                    prop = k.replace(f'{base_key}_', '')
                    value = trajectory_values[i]
                    if value is not None:
                        value = json.loads(value.decode('utf-8'))
                    trajectory.set_property(prop, value)
                return trajectory
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def get_property(self, trajectory_id: str, prop: TrajectoryProperties, compone_key=True):
        if compone_key is True:
            base_key = self.trajectory_prefix + '_' + trajectory_id
        else:
            base_key = trajectory_id
        key = f'{base_key}_{prop.value}'
        try:
            value = self.redis_connection.get(key)
            if value is None:
                return value
            else:
                return json.loads(value.decode('utf-8'))
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def get_task_waiting_time(self, task_id: str) -> float or None:
        key = self.task_waiting_time_prefix + '_' + task_id
        try:
            value = self.redis_connection.get(key)
            if value is not None:
                waiting_time = json.loads(value.decode('utf-8'))
                return waiting_time
            else:
                return None
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def get_if_not_none_or_wait_update(self, trajectory_id: str, prop: TrajectoryProperties,
                                       retry=0, max_retry=3, full_trajectory=False):
        if retry > max_retry:
            self.logger.error('No {} has been updated for trajectory {}'.format(prop, trajectory_id),
                              resource='RedisBackend')
            raise NoStateFoundForTrajectoryException(trajectory_id)
        else:
            if retry > 0:
                self.logger.debug('Get state has been retried {} times'.format(retry), resource='RedisBackend')
        trajectory_prop = self.get_property(trajectory_id, prop)
        self.logger.debug('Property {} has value {} for trajectory with id {}'
                          .format(prop, trajectory_prop, trajectory_id), resource='RedisBackend')
        if trajectory_prop is None:
            # wait
            base_key = self.compone_key(trajectory_id)
            subscribe_key = f'__keyspace@{self.redis_db}__:{base_key}_{prop.value}'
            try:
                self.logger.debug('Subscribing to {}'.format(subscribe_key), resource='RedisBackend')
                _ = self.queue.get(subscribe_key, timeout=3)
                self.logger.debug('{} should be ready, I am trying to get the trajectory again'.format(prop),
                                  resource='RedisBackend')
                trajectory_prop = self.get_property(trajectory_id, prop)
                if trajectory_prop is None:
                    self.logger.debug('{} is still None, I am trying to get the trajectory again'.format(prop),
                                      resource='RedisBackend')
                    return self.get_if_not_none_or_wait_update(trajectory_id, prop,
                                                               retry + 1, max_retry, full_trajectory)
                else:
                    if full_trajectory is True:
                        return self.get(trajectory_id)
                    else:
                        return trajectory_prop
            except TimeoutError:
                self.logger.debug('{} is not ready yet, I am trying to get the trajectory again'.format(prop),
                                  resource='RedisBackend')
                return self.get_if_not_none_or_wait_update(trajectory_id, prop, retry + 1, max_retry, full_trajectory)
        else:
            self.logger.debug('Returning trajectory property {} from trajectory with id {}'
                              .format(trajectory_prop, trajectory_id), resource='RedisBackend')
            if full_trajectory is True:
                return self.get(trajectory_id)
            else:
                return trajectory_prop

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def get_previous_trajectory(self, only_id=False) -> Trajectory or str or None:
        try:
            previous_trajectory_key = self.redis_connection.get(self.previous_trajectory_key)
            if previous_trajectory_key is None:
                return None
            previous_trajectory_key = previous_trajectory_key.decode('utf-8')
            if previous_trajectory_key == '0':
                # wait until a value is added to the previous trajectory key
                previous_trajectory_key = self._wait_for_previous_trajectory_key(max_retry=2)
            # we have the previous trajectory key, get the trajectory if only_id is False
            self.logger.debug('RedisTrajectoryBackend previous trajectory key = {}'.format(previous_trajectory_key),
                              resource='RedisBackend')
            if only_id is True:
                return previous_trajectory_key
            else:
                trajectory = self.get(trajectory_id=previous_trajectory_key, compone_key=False)
                return trajectory
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    def _wait_for_previous_trajectory_key(self, retry=0, max_retry=2):
        if retry > max_retry:
            self.logger.error('No {} has been found'.format(self.previous_trajectory_key), resource='RedisBackend')
            raise Exception('No previous trajectory key has been found')
        subscribe_key = f'__keyspace@{self.redis_db}__:{self.previous_trajectory_key}'
        try:
            self.logger.debug('Subscribing to {}'.format(subscribe_key), resource='RedisBackend')
            _ = self.queue.get(subscribe_key, timeout=5)
            previous_trajectory_key = self.get(self.previous_trajectory_key)
            if previous_trajectory_key is None or previous_trajectory_key.decode('utf-8') == '0':
                self.logger.warning('No previous trajectory key has been found in 5 seconds', resource='RedisBackend')
                return self._wait_for_previous_trajectory_key(retry + 1, max_retry)
            else:
                return previous_trajectory_key.decode('utf-8')
        except TimeoutError:
            self.logger.debug('{} is not ready yet, I am trying to get the trajectory again'
                              .format(self.previous_trajectory_key), resource='RedisBackend')
            return self._wait_for_previous_trajectory_key(retry + 1, max_retry)

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def set_previous_trajectory(self, trajectory_id: str):
        trajectory_key = self.compone_key(trajectory_id=trajectory_id)
        result = self._set(self.previous_trajectory_key, trajectory_key)
        self.logger.debug('Trajectory with id: {} saved as previous trajectory'.format(trajectory_id),
                          resource='RedisBackend')
        return result

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def get_all(self, key_pattern=None) -> list or None:
        try:
            pattern = key_pattern if key_pattern is not None else self.trajectory_prefix + '_*_id'
            keys = self.redis_connection.keys(pattern)
            trajectories_ids = self.redis_connection.mget(keys)
            trajectories_ids = [json.loads(t.decode('utf-8')) for t in trajectories_ids]
            trajectories = []
            for t_id in trajectories_ids:
                trajectories.append(self.get(t_id))
            return trajectories
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def delete(self, trajectory_id) -> int or None:
        base_key = self.trajectory_prefix + '_' + trajectory_id
        try:
            properties = Trajectory.get_trajectory_properties()
            keys = [f'{base_key}_{prop}' for prop in properties]
            return self.redis_connection.delete(*keys)
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    @retry_on_exceptions(max_retries=3, exceptions=(redis.ConnectionError, ))
    def delete_all(self, pattern):
        try:
            return self.redis_connection.delete(*self.redis_connection.keys(pattern))
        except redis.ResponseError as e:
            self.logger.error('Error while deleting pattern: {}'.format(pattern), resource='RedisBackend')
            self.logger.exception(e)
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return None

    def check_connection(self):
        try:
            return self.redis_connection.ping()
        except redis.ConnectionError as e:
            self.logger.error(e)
            return False

    def close(self):
        self.redis_connection.close()
        self.redis_connection.client().close()
        self.redis_connection.client().connection_pool.disconnect()


class RedisBufferBackend(RedisBackend):

    def __init__(self, size, config=None, logger=None, host=None):
        super(RedisBufferBackend, self).__init__(config, logger, host)
        self.redis_pipeline = self.redis_connection.pipeline()
        self.size = size
        if host is not None:
            self.config['connection']['host'] = host

    def push(self, key: str, value):
        try:
            self.redis_pipeline.rpush(key, value.encode('utf-8'))
            self.redis_pipeline.ltrim(key, -self.size, -1)
            self.redis_pipeline.execute()
            self.logger.debug(f'Push and trim successfully on key {key}')
            return True
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return False

    def get_buffer(self, key: str):
        try:
            results = self.redis_connection.lrange(key, 0, -1)
            if results is not None and len(results) > 0:
                return [r.decode('utf-8') for r in results]
            else:
                return []
        except redis.ConnectionError as e:
            self.logger.exception(e)
            return False
