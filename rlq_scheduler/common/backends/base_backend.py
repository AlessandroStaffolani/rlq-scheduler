from rlq_scheduler.common.utils.logger import get_logger
from rlq_scheduler.common.trajectory import Trajectory, TrajectoryProperties

DEFAULT_LOGGER = {'name': 'server',
                  'level': 20,  # 10=DEBUG, 20=INFO, 30=WARN, 40=ERROR
                  'handlers': [
                      {'type': 'console',
                       'parameters': None}
                  ]}


class BaseBackend(object):

    def __init__(self, config=None, logger=None):
        self.config = config
        self.logger = logger if logger is not None else get_logger(DEFAULT_LOGGER)

    def save(self, key: str, value):
        pass

    def save_list(self, key: str, values):
        pass

    def update(self, key: str, value):
        pass

    def append_to_list(self, key: str, values):
        pass

    def get(self, key: str):
        pass

    def get_list(self, key: str):
        pass

    def get_all(self, key_pattern=None):
        pass

    def get_keys(self, key_pattern=None):
        pass

    def delete(self, key: str):
        pass

    def delete_all(self, pattern):
        pass

    def check_connection(self):
        pass

    def close(self):
        pass


class BaseBufferBackend(BaseBackend):

    def __init__(self, size, config=None, logger=None):
        super(BaseBufferBackend, self).__init__(config, logger)
        self.size = size

    def push(self, key: str, value):
        pass

    def get_buffer(self, key: str):
        pass


class BaseTrajectoryBackend(BaseBackend):

    def __init__(self, config=None, logger=None):
        super(BaseTrajectoryBackend, self).__init__(logger)
        self.config = config
        self.trajectory_prefix = self.config['trajectory_prefix'] if self.config is not None else 'trajectory'
        self.previous_trajectory_key = self.config['previous_trajectory_key'] if self.config is not None \
            else 'previous_trajectory'
        self.task_waiting_time_prefix = self.config['task_waiting_time_prefix'] if self.config is not None \
            else 'task_waiting_time'

    def save(self, trajectory_id: str,  trajectory: Trajectory, use_setnx=False):
        pass

    def save_property(self, trajectory_id: str, value, prop: TrajectoryProperties, compone_key=True):
        pass

    def set_task_waiting_time(self, task_id: str, started, waited=None):
        pass

    def update(self, trajectory_id: str, trajectory: Trajectory):
        pass

    def update_property(self, trajectory_id: str, value, prop: TrajectoryProperties, compone_key=True):
        pass

    def compone_key(self, trajectory_id: str):
        pass

    def get(self, trajectory_id: str, compone_key=True):
        pass

    def get_property(self, trajectory_id: str, prop: TrajectoryProperties, compone_key=True):
        pass

    def get_task_waiting_time(self, task_id: str) -> float or None:
        pass

    def get_if_not_none_or_wait_update(self,
                                       trajectory_id: str,
                                       prop: TrajectoryProperties,
                                       retry: int = 0,
                                       max_retry: int = 2,
                                       full_trajectory=False) -> Trajectory:
        pass

    def get_previous_trajectory(self, only_id=False) -> Trajectory or str or None:
        pass

    def set_previous_trajectory(self, trajectory_id: str):
        pass

    def get_all(self, key_pattern=None):
        pass

    def delete(self, trajectory_id: str):
        pass

    def delete_all(self, pattern):
        pass

    def check_connection(self):
        pass

    def close(self):
        pass
