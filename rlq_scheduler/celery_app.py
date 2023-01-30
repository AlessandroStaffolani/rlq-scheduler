from __future__ import absolute_import, unicode_literals

import os

from celery import Celery
from dotenv import load_dotenv

from rlq_scheduler.common.config_helper import GlobalConfigHelper
from rlq_scheduler.common.utils.filesystem import ROOT_DIR
from rlq_scheduler.common.utils.logger import get_logger

load_dotenv(dotenv_path=os.path.join(ROOT_DIR, '.env'))

CELERY_CONFIG_FILEPATH = os.environ.get('GLOBAL_CONFIG_FILEPATH') or 'config/global.yml'
BROKER_SERVICE_HOST = os.environ.get('BROKER_SERVICE_SERVICE_HOST') or 'localhost'
BROKER_SERVICE_PORT = os.environ.get('BROKER_SERVICE_SERVICE_PORT') or 6379
BROKER_SERVICE_PORT = int(BROKER_SERVICE_PORT)

config: GlobalConfigHelper or None = None
logger = None


def configure_celery_application():
    global config
    global logger
    if config is None:
        config = GlobalConfigHelper(config_path=CELERY_CONFIG_FILEPATH)
    if logger is None:
        logger = get_logger(config.logger())


configure_celery_application()
if logger is None:
    raise Exception('Some of the components required by celery are None. Configure properly the configuration file')

logger.info('Connecting celery to broker at: {}'.format(BROKER_SERVICE_HOST))

app = Celery('ServiceBroker',
             # if db changes it has to changes also on flower deployments and deployer_manager at row: 404
             broker=f'redis://{BROKER_SERVICE_HOST}:{BROKER_SERVICE_PORT}/0',
             # backend=f'redis://{BROKER_SERVICE_HOST}:{BROKER_SERVICE_PORT}/0',
             include=['service_broker.tasks.tasks', 'service_broker.tasks.task_broker'])

# Optional configuration, see the application user guide.
app.conf.update(
    result_expires=3600,
    enable_utc=True,
    timezone='Europe/Rome',
    celery_accept_content=['json'],
    celery_task_serializer='json',
    celery_result_serializer='json',
    celery_send_events=True,
    celery_create_missing_queues=True,
    task_send_sent_event=True,
    redis_max_connections=1000,
    task_ignore_result=True,
    task_store_errors_even_if_ignored=True,
    event_queue_expires=60 * 20,  # 20 minutes,
    broker_heartbeat=0
)

if __name__ == '__main__':
    app.start()
