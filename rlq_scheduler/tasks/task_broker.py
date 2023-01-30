from __future__ import absolute_import, unicode_literals, division, print_function

from copy import deepcopy

from rlq_scheduler.common.stats import StatsBackend
from rlq_scheduler.tasks.tasks import *

logger = get_task_logger(__name__)

requests = None
global_config: GlobalConfigHelper or None = None
stats_backend: StatsBackend or None = None
history_index = {}


@app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 5}, default_retry_delay=10)
def task_broker(self, name, parameters):
    global global_config
    global stats_backend
    if global_config is None:
        global_config_path = os.environ.get('GLOBAL_CONFIG_FILENAME') or 'config/global.yml'
        global_config = GlobalConfigHelper(config_path=global_config_path)
    if stats_backend is None:
        stats_backend = StatsBackend(global_config=global_config, logger=None, host=None)
    self_id = self.request.id
    if self_id not in history_index:
        history_index[self_id] = 1
    else:
        history_index[self_id] += 1
        logger.warning('Task {} has been received more than once.'
                       ' Maybe it failed and it is retried or may there is an error'.format(self_id))
    available_worker_classes = global_config.available_worker_classes()
    task_class = parameters['task_class']
    start = time.time()
    action, current_run_code = request_action(self_id, task_class=task_class, task_parameters=parameters)
    end = time.time()
    if action['label'] in available_worker_classes:
        queue = action['label']
    else:
        if action['index'] < len(available_worker_classes):
            queue = available_worker_classes[action['index']]
        else:
            raise Exception(f'Action {action} not available')
    switcher = {
        'fake_task': fake_task,
        'ram_task': ram_task,
        'cpu_task': cpu_task,
        'ram_and_cpu_task': ram_and_cpu_task,
        'disk_task': disk_task,
        'disk_and_computation_task': disk_and_computation_task,
        'waste_clock': waste_clock,
        'exception_task': exception_task,
        'google_trace_task': google_trace_task,
    }
    new_task_id = f'{self_id}.exec'
    if name in switcher:
        # join_task_to_trajectory(previous_task_id=self.request.id, next_task_id=new_task_id)
        result = switcher[name].apply_async(kwargs=parameters, queue=queue, task_id=new_task_id)
        logger.info('Current task UUID: {} | task assigned to {} queue | task UUID: {}'
                    .format(self.request.id, queue, result.id))
        stats_backend.save_stats_group_property(
            stats_run_code=current_run_code,
            prop='full_time_get_action',
            value=end - start,
            as_list=True
        )
    else:
        logger.error('Task name {} requested is not available'.format(name))


def prepare_url(config_key):
    global global_config
    if global_config is not None:
        api_config = global_config.api_resource_endpoint(config_key)
        protocol = api_config['protocol']
        host = api_config['host']
        port = api_config['port']
        return f'{protocol}://{host}:{port}'
    else:
        raise AttributeError('Config object is not initialized')


def request_action(task_id, task_class, task_parameters, retry=0, max_retries=3):
    global requests
    if requests is None:
        import requests as requests_module
        requests = requests_module
    if retry > 0:
        logger.info('Request action retried {} times'.format(retry))
    url = f'{prepare_url("agent")}/api/agent/action/{task_id}'
    task_params = deepcopy(task_parameters)
    del task_params['task_class']
    params = {'task_class': task_class, 'task_params': task_params}
    logger.debug('Url is = {}'.format(url))
    response = requests.get(
        url,
        params=params,
        headers={"Content-Type": "application/json"}
    )
    logger.info('Response from agent = {}'.format(response))
    if response.status_code == 200:
        response_obj = response.json()
        logger.info('Agent selected action {}'.format(response_obj))
        return response_obj['action'], response_obj['current_run_code']
    else:
        if retry > max_retries:
            logger.error('Retried 3 times to get action from Agent')
            raise Exception('Agent unreachable')
        else:
            logger.warning('Agent returned status code different from 200. Retrying for the {} time'.format(retry))
            return request_action(task_id, task_class, retry + 1, max_retries)
