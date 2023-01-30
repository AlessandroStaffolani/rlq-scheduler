import os

from torch.utils.tensorboard import SummaryWriter

from rlq_scheduler.common.utils.filesystem import get_absolute_path, create_directory
from rlq_scheduler.common.utils.logger import get_logger

LOGGER_CONFIG = {
    'name': '',
    'level': 20,
    'handlers': [
        {'type': 'console', 'parameters': None}
    ]
}


def check_env_variables():
    variables = ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_REGION',
                 'S3_ENDPOINT', 'S3_USE_HTTPS', 'S3_VERIFY_SSL']
    for var in variables:
        if os.getenv(var) is None:
            raise AttributeError('Env variable: {} has not been set'.format(var))


class TensorboardWrapper:

    def __init__(self, log_dir, transport='s3', logger=None, *args, **kwargs):
        self.transport = transport
        self.logger = logger if logger is not None else get_logger(LOGGER_CONFIG)
        if self.transport == 's3':
            check_env_variables()
            self.log_dir = f's3://{log_dir}'
        elif self.transport == 'file':
            self.log_dir = get_absolute_path(log_dir)
            create_directory(self.log_dir)
        else:
            raise AttributeError('Invalid transport.')
        self.logger.debug('Log dir: {}'.format(self.log_dir), resource='TensorboardWrapper')
        self.writer = SummaryWriter(log_dir=self.log_dir, *args, **kwargs)
        self.logger.info('Tensorboard enabled using transport: {}'.format(self.transport),
                         resource='TensorboardWrapper')

    def add_scalar(self, tag, value, step, *args, **kwargs):
        self.writer.add_scalar(tag, value, step, *args, **kwargs)
        self.logger.debug('Added scalar to tensorboard with tag: {} | value: {} | step: {}'.format(tag, value, step),
                          resource='TensorboardWrapper')

    def close(self):
        self.writer.close()
        self.logger.info('Tensorboard writer has been closed', resource='TensorboardWrapper')
