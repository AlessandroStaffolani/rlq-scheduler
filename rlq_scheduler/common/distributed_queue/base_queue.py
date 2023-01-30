from rlq_scheduler.common.utils.logger import get_logger

DEFAULT_LOGGER = {'name': 'server',
                  'level': 20,  # 10=DEBUG, 20=INFO, 30=WARN, 40=ERROR
                  'handlers': [
                      {'type': 'console',
                       'parameters': None}
                  ]}


class BaseDistributedQueue:

    def __init__(self, config=None, logger=None):
        self.logger = logger if logger is not None else get_logger(DEFAULT_LOGGER)
        self.config = config

    def push(self, key, value, push_if_not_present=False):
        pass

    def get(self, key, timeout=60):
        pass

    def subscribe(self, key, callback):
        pass

    def close(self):
        pass
