import requests
import time
from logging import Logger

from rlq_scheduler.common.config_helper import GlobalConfigHelper
from rlq_scheduler.common.utils.request_utils import prepare_url
from rlq_scheduler.common.system_status import SystemStatus, ResourceStatus


def wait_system_manager(global_config: GlobalConfigHelper, logger: Logger, timeout=30):
    logger.info('Checking SystemManager status')
    count = 1
    is_ready = is_system_manager_ready(global_config, logger)
    while is_ready is False and count < timeout:
        sleep = 2 ** count
        count += 1
        logger.debug('SystemManager is not yet. Waiting {} seconds before trying again'.format(sleep))
        time.sleep(sleep)
        is_ready = is_system_manager_ready(global_config, logger)
    if is_ready:
        logger.info('SystemManager is ready')
    else:
        logger.warning('SystemManager is not ready after {} seconds'.format(timeout))


def is_system_manager_ready(global_config: GlobalConfigHelper, logger: Logger):
    base_url = prepare_url('system_manager', global_config)
    url = f'{base_url}/api/health/check'
    logger.debug('Requesting environment status to HealthTool using url {}'.format(url))
    response = requests.get(
        url,
        headers={"Content-Type": "application/json"}
    )
    logger.info('SystemManager response is {}'.format(response))
    if response.status_code == 200:
        res_obj = response.json()
        system_status = ResourceStatus(res_obj['status'])
        if system_status == ResourceStatus.OK:
            logger.debug('SystemManager response object is = {}'.format(res_obj))
            return True
        else:
            logger.warning('SystemManager response object is = {}'.format(res_obj))
    return False


def is_environment_ready(global_config: GlobalConfigHelper, logger: Logger, host=None, use_kube_port=False):
    base_url = prepare_url('system_manager', global_config, host=host, use_kube_port=use_kube_port)
    url = f'{base_url}/api/system/health/check'
    logger.debug('Requesting environment status to HealthTool using url {}'.format(url))
    response = requests.get(
        url,
        headers={"Content-Type": "application/json"}
    )
    logger.info('SystemManager response is {}'.format(response))
    if response.status_code == 200:
        res_obj = response.json()
        system_status = SystemStatus(res_obj['status'])
        if system_status == SystemStatus.READY:
            logger.debug('SystemManager response object is = {}'.format(res_obj))
            return True
        else:
            logger.warning('SystemManager response object is = {}'.format(res_obj))
    return False
