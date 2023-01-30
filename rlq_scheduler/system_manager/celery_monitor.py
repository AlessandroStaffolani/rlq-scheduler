from copy import deepcopy

from rlq_scheduler.common.config_helper import GlobalConfigHelper
from rlq_scheduler.common.system_status import ResourceStatus


class CeleryMonitor:

    def __init__(self, celery_app, global_config: GlobalConfigHelper, logger):
        self.celery_app = celery_app
        self.global_config = global_config
        self.logger = logger

    def status(self):
        resources_to_check = {
            self.global_config.task_broker_worker_name(): 1
        }
        for worker_class in self.global_config.available_worker_classes():
            resources_to_check[worker_class] = self.global_config.worker_class_replicas(worker_class)
        status = ResourceStatus.NOT_READY
        message = 'celery is not running'
        resources_initial = deepcopy(resources_to_check)
        unavailable_resources = {}
        available_resources = {}
        try:
            inspection = self.celery_app.control.inspect()
            ping = inspection.ping()
            if ping is not None:
                for worker_fullname, info in ping.items():
                    self.check_single_worker_status(worker_fullname, info, resources_to_check)
                is_ready = True
                for key, val in resources_to_check.items():
                    if val != 0:
                        is_ready = False
                if is_ready is True:
                    status = ResourceStatus.RUNNING
                    message = 'celery is running properly'
                    available_resources = deepcopy(resources_initial)
                else:
                    status = ResourceStatus.NOT_READY
                    message = 'celery is reachable but some celery workers is unreachable'
                    available_resources = deepcopy(resources_initial)
                    for key, val in resources_to_check.items():
                        available_resources[key] -= val
                unavailable_resources = deepcopy(resources_to_check)
        except Exception as e:
            status = ResourceStatus.ERROR
            message = e
        finally:
            health = {
                'status': status,
                'message': message,
                'available_resources': available_resources,
                'unavailable_resources': unavailable_resources
            }
            return health

    def check_single_worker_status(self, worker_fullname, worker_info, resources_to_check):
        for worker, res_to_check in resources_to_check.items():
            if worker in worker_fullname:
                self.logger.debug('Celery worker: {} ping response: {}'.format(worker, worker_info),
                                  resource='CeleryMonitor')
                if worker_info['ok'] == 'pong':
                    resources_to_check[worker] -= 1
                return
