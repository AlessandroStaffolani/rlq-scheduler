import functools
import traceback
from copy import deepcopy
from multiprocessing.pool import ThreadPool

from kubernetes import config as kube_config

from rlq_scheduler.common.config_helper import GlobalConfigHelper, DeployerManagerConfigHelper, BaseConfigHelper
from rlq_scheduler.common.exceptions import DeployStepException
from rlq_scheduler.common.utils.config_loaders import load_yaml_config, load_multiple_yamls_from_file
from rlq_scheduler.common.utils.logger import get_logger
from rlq_scheduler.deployer_manager.common import DeploymentStatus, MethodResult, StepResult, \
    KubeResource, ResourceMapper, ActionResult, label_to_label_selector
from rlq_scheduler.deployer_manager.kube_wrapper import list_cluster_nodes, add_common_labels, \
    apply_resource, handle_async_requests, \
    delete_resource, wait_for_resource_running, sort_resources, get_deployment_resource_index, delete_many_resources, \
    wait_for_resource_deletion, list_many_resources, update_deployment_env_variable


# get all: kubectl -n service-broker get po,deploy,sts,pvc,pv,svc,cm,secret -l "app.kubernetes.io/product=service-broker"
# delete all: kubectl -n service-broker delete po,deploy,sts,pvc,pv,svc,cm,secret -l "app.kubernetes.io/product=service-broker"


def step_decorator(step_name):
    def wrap(func):
        @functools.wraps(func)
        def wrapper_function(self, *args, **kwargs):
            logger = self.logger
            result = StepResult(step=step_name, success=True, reason='SUCCESS')
            try:
                logger.info('Starting step "{}"'.format(result.step))
                result = func(self, result, *args, **kwargs)
                if result.success is True:
                    logger.info('Step "{}" completed with result: "{}"'.format(result.step, result.reason))
                else:
                    logger.error('Step "{}" completed with result: "{}" and error trace: {}'
                                 .format(result.step, result.reason, result.trace))
                return result
            except Exception as e:
                logger.error(e)
                logger.exception(e)
                result.success = False
                result.reason = str(e)
                result.trace = traceback.format_exc()
                return result

        return wrapper_function

    return wrap


def async_call(func):
    @functools.wraps(func)
    def wrapper_function(self, *args, **kwargs):
        if self.script_mode is True:
            return func(self, *args, **kwargs)
        else:
            return self.pool.apply_async(func, args=(self, *args), kwds=kwargs)

    return wrapper_function


class DeployerManager:

    def __init__(self,
                 config: DeployerManagerConfigHelper,
                 global_config: GlobalConfigHelper,
                 logger=None,
                 script_mode=False
                 ):
        self.name = 'DeployerManager'
        self.config: DeployerManagerConfigHelper = config
        self.global_config: GlobalConfigHelper = global_config
        self.script_mode = script_mode
        self.logger = logger if logger is not None else get_logger(config.logger())
        self.status = DeploymentStatus.NOT_INITIALIZED
        if self.config.kube_config_mode() == 'out':
            kube_config.load_kube_config(config_file=config.kube_config_file())
        elif self.config.kube_config_mode() == 'in':
            kube_config.load_incluster_config()
        self.logger.info('Initialized kube config using {}'.format(config.kube_config_file()))
        self.kubernetes_cluster_endpoints = []
        self.kubernetes_deployed_resources = {
            KubeResource.DEPLOYMENT: [],
            KubeResource.STATEFUL_SET: [],
            KubeResource.DAEMON_SET: [],
            KubeResource.CONFIG_MAP: [],
            KubeResource.SECRET: [],
            KubeResource.SERVICE: [],
            KubeResource.PERSISTENT_VOLUME_CLAIM: []
        }

        self.steps = [
            self._deploy_namespace,
            self._deploy_configmap_load_step,
            self._deploy_config_maps_step,
            self._docker_registry_secret_step,
            self._minio_secret_step,
            self._mongo_secret_step,
            self._deploy_redis_queue_step,
            self._deploy_redis_shared_memory_step,
            self._deploy_rlq_resources,
            self._deploy_system_manager_step,
        ]
        self.pool = ThreadPool(processes=self.config.deployer_manager_pool_size())
        self._check_system_status()

    def _check_system_status(self):
        self.system_info()
        label_selector = label_to_label_selector(self.config.kube_common_labels()[0])
        for kind, _ in self.kubernetes_deployed_resources.items():
            res = list_many_resources(kind, label_selector, namespace=self.config.kube_namespace(), logger=self.logger)
            if res.success is True:
                self.logger.info('For kind {} resources are: {}'.format(kind, res.value))
                self.kubernetes_deployed_resources[kind] = res.value
            else:
                self.logger.error('Error trying to get resources of kind {}. Reason = {}'.format(kind, res.reason))
        resources_to_deploy = self.config.deployments_number() + len(self.global_config.available_worker_classes())
        deployed_resources = len(self.kubernetes_deployed_resources[KubeResource.DEPLOYMENT]) + \
                             len(self.kubernetes_deployed_resources[KubeResource.STATEFUL_SET])
        if resources_to_deploy == deployed_resources:
            self.status = DeploymentStatus.READY
        self.logger.info('System status is: {}'.format(self.status))

    def system_status(self):
        return {
            'status': self.status,
            'kubernetes_cluster_endpoints': self.kubernetes_cluster_endpoints,
            'deployed_resources': self.kubernetes_deployed_resources
        }

    def system_info(self):
        self.kubernetes_cluster_endpoints = list_cluster_nodes(self.logger)

    def _execute_deployment_steps(self):
        try:
            for i, step in enumerate(self.steps):
                self.logger.info('Step {}/{}'.format(i + 1, len(self.steps)))
                result = step()
                DeployerManager._verify_step(result)
                self.logger.info('Step {}/{}: {}'.format(i + 1, len(self.steps), result.reason))
            return True
        except DeployStepException as e:
            self.status = DeploymentStatus.ERROR
            self.logger.error(e)
            return str(e)

    @async_call
    def deploy(self) -> ActionResult:
        action_result = ActionResult(action='Deploy ServiceBroker system', success=True, reason='SUCCESS')
        extras = {}
        try:
            self.status = DeploymentStatus.DEPLOYING
            self.logger.info('{} is starting the deployment of the ServiceBroker system'.format(self.name))
            result = self._execute_deployment_steps()
            if result is True:
                self.status = DeploymentStatus.READY
                self.logger.info('{} completed the deployment of the ServiceBroker system'.format(self.name))
                self.logger.info('Deployed resources: {}'.format(self.kubernetes_deployed_resources))
                extras['deployed_resources'] = self.kubernetes_deployed_resources
            else:
                self.logger.error('{} failed to deploy the ServiceBroker system'.format(self.name))
                action_result.success = False
                action_result.reason = result
        except Exception as e:
            self.logger.error(e)
            action_result.success = False
            action_result.reason = str(e)
            action_result.trace = traceback.format_exc()
        finally:
            extras['system_status'] = self.status
            action_result.extras = extras
            return action_result

    @async_call
    def clean_up(self) -> ActionResult:
        action_result = ActionResult(action='CleanUp ServiceBroker system', success=True, reason='SUCCESS')
        extras = {}
        resources_backup = deepcopy(self.kubernetes_deployed_resources)
        try:
            self.logger.info('{} is starting the CleanUp procedure of the ServiceBroker system'.format(self.name))
            self.logger.info('The following resources are going to be removed: {}'
                             .format(self.kubernetes_deployed_resources))
            self.status = DeploymentStatus.CLEANING
            step_result: StepResult = self._clean_up_system_step()
            DeployerManager._verify_step(step_result)
            self.logger.info('{} step completed with success'.format(step_result.step))
            self.status = DeploymentStatus.NOT_INITIALIZED
            extras['removed_resources'] = resources_backup
        except Exception as e:
            self.status = DeploymentStatus.ERROR
            self.logger.error(e)
            action_result.success = False
            action_result.reason = str(e)
        finally:
            extras['system_status'] = self.status
            action_result.extras = extras
            return action_result

    @step_decorator(step_name='CleanUp System')
    def _clean_up_system_step(self, result: StepResult) -> StepResult:
        deployed_resources = 0
        label_selector = label_to_label_selector(self.config.kube_common_labels()[0])
        for _, l in self.kubernetes_deployed_resources.items():
            deployed_resources += len(l)
        if deployed_resources > 0:
            for kind, resources_list in self.kubernetes_deployed_resources.items():
                if kind != KubeResource.SERVICE:
                    delete_many_resources(kind, label_selector, namespace=self.config.kube_namespace(),
                                          logger=self.logger)
                else:
                    for service_name in resources_list:
                        delete_resource(kind, service_name, namespace=self.config.kube_namespace(), logger=self.logger)
                for name in resources_list:
                    mapper = ResourceMapper(kind)
                    wait_for_resource_deletion(mapper, name, namespace=self.config.kube_namespace(),
                                               timeout=60, log_interval=5, logger=self.logger)
            self.kubernetes_deployed_resources = {
                KubeResource.DEPLOYMENT: [],
                KubeResource.STATEFUL_SET: [],
                KubeResource.DAEMON_SET: [],
                KubeResource.CONFIG_MAP: [],
                KubeResource.SECRET: [],
                KubeResource.SERVICE: [],
                KubeResource.PERSISTENT_VOLUME_CLAIM: []
            }
            return result
        else:
            result.success = False
            result.reason = 'No deployed resources'
            return result

    @step_decorator(step_name='ServiceBroker namespace')
    def _deploy_namespace(self, result: StepResult) -> StepResult:
        namespace_name = self.config.kube_namespace()
        namespace_definition = {
            'apiVersion': 'v1',
            'kind': 'Namespace',
            'metadata':
                {'name': namespace_name}
        }
        res: MethodResult = apply_resource(
            body=namespace_definition,
            logger=self.logger,
            replace_if_exists=False,
            async_req=False
        )
        result.from_method_result(res)
        return result

    @step_decorator(step_name='ConfigMaps load')
    def _deploy_configmap_load_step(self, result: StepResult) -> StepResult:
        async_threads = []
        for path in self.config.config_maps_to_load():
            cmap = load_yaml_config(path)
            cmap = add_common_labels(self.config.kube_common_labels(), cmap)
            self._add_resource_to_kubernetes_deployed_resources(
                kind=KubeResource(cmap['kind']),
                name=cmap['metadata']['name'])
            async_threads.append(apply_resource(
                body=cmap,
                namespace=self.config.kube_namespace(),
                logger=self.logger,
                replace_if_exists=True,
                async_req=True
            ))
            self.logger.info('Scheduled creation of ConfigMap: "{}"'.format(cmap['metadata']['name']))

        res: MethodResult = handle_async_requests(async_threads, logger=self.logger)
        if res.success is False:
            result.success = False
            result.reason = res.reason
        else:
            self.logger.info('All the scheduled resources for step "{}" have been created'.format(result.step))
        return result

    @step_decorator(step_name='ConfigMaps creation')
    def _deploy_config_maps_step(self, result: StepResult) -> StepResult:
        async_threads = []
        for config_props in self.config.config_maps_to_create():
            config_helper = BaseConfigHelper(config_path=config_props['file'])
            cmap = config_helper.to_config_map(**config_props['cmap_args'])
            cmap = add_common_labels(self.config.kube_common_labels(), cmap)
            self._add_resource_to_kubernetes_deployed_resources(
                kind=KubeResource(cmap['kind']),
                name=cmap['metadata']['name'])
            async_threads.append(apply_resource(
                body=cmap,
                namespace=self.config.kube_namespace(),
                logger=self.logger,
                replace_if_exists=True,
                async_req=True
            ))
            self.logger.info('Scheduled creation of ConfigMap: "{}"'.format(config_props['cmap_args']['name']))

        res: MethodResult = handle_async_requests(async_threads, logger=self.logger)
        if res.success is False:
            result.success = False
            result.reason = res.reason
        else:
            self.logger.info('All the scheduled resources for step "{}" have been created'.format(result.step))
        return result

    @step_decorator(step_name='Redis Queue Deployment')
    def _deploy_redis_queue_step(self, result: StepResult) -> StepResult:
        redis_resources = load_multiple_yamls_from_file(self.config.redis_queue_deployment_file())
        return self._create_kubernetes_resources(
            result=result,
            kube_resources=redis_resources,
            delete_if_exists=True,
            wait_running=True,
            deployment_kind=KubeResource.DEPLOYMENT
        )

    @step_decorator(step_name='Redis Shared Memory Deployment')
    def _deploy_redis_shared_memory_step(self, result: StepResult) -> StepResult:
        redis_resources = load_multiple_yamls_from_file(self.config.redis_shared_memory_deployment_file())
        return self._create_kubernetes_resources(
            result=result,
            kube_resources=redis_resources,
            delete_if_exists=True,
            wait_running=True,
            deployment_kind=KubeResource.DEPLOYMENT
        )

    @step_decorator(step_name='Docker registry secret')
    def _docker_registry_secret_step(self, result: StepResult) -> StepResult:
        docker_secret = load_yaml_config(self.config.docker_registry_secret_file())
        docker_secret = add_common_labels(self.config.kube_common_labels(), docker_secret)
        self._add_resource_to_kubernetes_deployed_resources(
            kind=KubeResource(docker_secret['kind']),
            name=docker_secret['metadata']['name'])
        res: MethodResult = apply_resource(
            body=docker_secret,
            namespace=self.config.kube_namespace(),
            logger=self.logger,
            replace_if_exists=True
        )
        result.success = res.success
        result.reason = res.reason if res.reason is not None else 'SUCCESS'
        return result

    @step_decorator(step_name='Minio secret')
    def _minio_secret_step(self, result: StepResult) -> StepResult:
        minio_secret = load_yaml_config(self.config.minio_secret_file())
        minio_secret = add_common_labels(self.config.kube_common_labels(), minio_secret)
        self._add_resource_to_kubernetes_deployed_resources(
            kind=KubeResource(minio_secret['kind']),
            name=minio_secret['metadata']['name'])
        res: MethodResult = apply_resource(
            body=minio_secret,
            namespace=self.config.kube_namespace(),
            logger=self.logger,
            replace_if_exists=True
        )
        result.success = res.success
        result.reason = res.reason if res.reason is not None else 'SUCCESS'
        return result

    @step_decorator(step_name='Mongo secret')
    def _mongo_secret_step(self, result: StepResult) -> StepResult:
        mongo_secret = load_yaml_config(self.config.mongo_secret_file())
        mongo_secret = add_common_labels(self.config.kube_common_labels(), mongo_secret)
        self._add_resource_to_kubernetes_deployed_resources(
            kind=KubeResource(mongo_secret['kind']),
            name=mongo_secret['metadata']['name'])
        res: MethodResult = apply_resource(
            body=mongo_secret,
            namespace=self.config.kube_namespace(),
            logger=self.logger,
            replace_if_exists=True
        )
        result.success = res.success
        result.reason = res.reason if res.reason is not None else 'SUCCESS'
        return result

    @step_decorator(step_name='Deploy ServiceBroker Resources')
    def _deploy_rlq_resources(self, result: StepResult) -> StepResult:
        self.logger.info('Loading and preparing ServiceBroker deployment resources')
        # flower
        flower_resources = load_multiple_yamls_from_file(self.config.flower_deployment_file())
        # update flower command
        resources = []
        for r in flower_resources:
            if KubeResource(r['kind']) == KubeResource.DEPLOYMENT:
                flower_command = ['flower', f'--broker=redis://redis.{self.config.kube_namespace()}:6379/0']
                r['spec']['template']['spec']['containers'][0]['command'] = flower_command
            resources.append(r)
        flower_resources = resources

        # task_broker
        task_broker_resources = load_multiple_yamls_from_file(self.config.task_broker_deployment_file())
        task_broker_resources = [r for r in task_broker_resources]
        deployment_index = get_deployment_resource_index(task_broker_resources)
        deployment = task_broker_resources[deployment_index]
        deployment_env = deployment['spec']['template']['spec']['containers'][0]['env']
        for env in deployment_env:
            if env['name'] == 'WORKER_NAME':
                env['value'] = self.global_config.task_broker_worker_name()
            elif env['name'] == 'WORKER_QUEUES':
                env['value'] = self.global_config.task_broker_queue_name()

        # workers
        worker_template_resources = load_multiple_yamls_from_file(self.config.worker_class_template_deployment_file())
        worker_template_resources = [r for r in worker_template_resources]
        worker_deployments = self._create_worker_deployments(worker_template_resources)

        # Task Generator
        task_generator_resources = load_multiple_yamls_from_file(self.config.task_generator_deployment_file())
        task_generator_resources = [r for r in task_generator_resources]

        # Agent
        agent_resources = load_multiple_yamls_from_file(self.config.agent_deployment_file())
        agent_resources = [r for r in agent_resources]

        # Trajectory Collector
        trajectory_collector_resources = load_multiple_yamls_from_file(
            self.config.trajectory_collector_deployment_file())
        trajectory_collector_resources = [r for r in trajectory_collector_resources]

        rlq_resources = flower_resources + task_broker_resources + worker_deployments + \
                                   task_generator_resources + agent_resources + trajectory_collector_resources

        for resource in rlq_resources:
            if KubeResource(resource['kind']) == KubeResource.DEPLOYMENT or \
                    KubeResource(resource['kind']) == KubeResource.STATEFUL_SET:
                self.logger.debug('Updating BROKER_SERVICE_SERVICE_HOST env variable for resource: {}'
                                  .format(resource['metadata']['name']))
                self._set_custom_image_version(resource)
                res: MethodResult = update_deployment_env_variable(
                    body=resource,
                    env_name='BROKER_SERVICE_SERVICE_HOST',
                    env_value='redis.{}'.format(self.config.kube_namespace()),
                    logger=self.logger
                )
                if res.success is False:
                    result.success = False
                    result.reason = res.reason
                    return result
                else:
                    self.logger.debug(
                        'Updated BROKER_SERVICE_SERVICE_HOST env variable for resource: {} with result: {}'
                            .format(resource['metadata']['name'], resource))

        return self._create_kubernetes_resources(
            result=result,
            kube_resources=rlq_resources,
            delete_if_exists=True,
            wait_running=True,
            deployment_kind=KubeResource.DEPLOYMENT
        )

    @step_decorator(step_name='Deploy SystemManager')
    def _deploy_system_manager_step(self, result: StepResult) -> StepResult:
        system_manager_resources = load_multiple_yamls_from_file(self.config.system_manager_deployment_file())

        resources = []
        for resource in system_manager_resources:
            if KubeResource(resource['kind']) == KubeResource.DEPLOYMENT:
                self.logger.debug('Updating BROKER_SERVICE_SERVICE_HOST env variable for resource: {}'
                                  .format(resource['metadata']['name']))
                self._set_custom_image_version(resource)
                res: MethodResult = update_deployment_env_variable(
                    body=resource,
                    env_name='BROKER_SERVICE_SERVICE_HOST',
                    env_value='redis.{}'.format(self.config.kube_namespace()),
                    logger=self.logger
                )
                if res.success is False:
                    result.success = False
                    result.reason = res.reason
                    return result
                else:
                    self.logger.debug(
                        'Updated BROKER_SERVICE_SERVICE_HOST env variable for resource: {} with result: {}'
                            .format(resource['metadata']['name'], resource))
            resources.append(resource)

        return self._create_kubernetes_resources(
            result=result,
            kube_resources=resources,
            delete_if_exists=True,
            wait_running=True,
            deployment_kind=KubeResource.DEPLOYMENT
        )

    def _create_worker_deployments(self, worker_template_resources):
        deployments = []
        for worker_class in self.global_config.available_worker_classes():
            resources_limits = self.global_config.worker_class_resources_limits(worker_class)
            sts_name = worker_class.replace('_', '-')
            svc_name = f'{sts_name}-svc'
            for resource in worker_template_resources:
                if KubeResource(resource['kind']) == KubeResource.STATEFUL_SET:
                    # Prepare worker deployment
                    worker_class_sts = deepcopy(resource)
                    worker_class_sts['metadata']['name'] = sts_name
                    worker_class_sts['metadata']['labels']['app.kubernetes.io/name'] = sts_name
                    worker_class_sts['metadata']['labels']['class'] = worker_class
                    worker_class_sts['spec']['replicas'] = self.global_config.worker_class_replicas(worker_class)
                    worker_class_sts['spec']['selector']['matchLabels']['app.kubernetes.io/name'] = sts_name
                    worker_class_sts['spec']['serviceName'] = svc_name
                    worker_class_sts['spec']['template']['metadata']['labels']['app.kubernetes.io/name'] = sts_name
                    worker_class_sts['spec']['template']['metadata']['labels']['class'] = worker_class
                    deployment_container = worker_class_sts['spec']['template']['spec']['containers'][0]
                    deployment_env = worker_class_sts['spec']['template']['spec']['containers'][0]['env']
                    for env in deployment_env:
                        if env['name'] == 'WORKER_NAME':
                            env['value'] = worker_class
                        elif env['name'] == 'WORKER_QUEUES':
                            env['value'] = worker_class
                    # set resources
                    deployment_container['resources'] = {
                        'requests': {
                            'cpu': resources_limits['cpu'],
                            'memory': resources_limits['memory']
                        },
                        'limits': {
                            'cpu': resources_limits['cpu'],
                            'memory': resources_limits['memory']
                        }
                    }
                    # set pvc name
                    # deployment_pvc = worker_class_sts['spec']['volumeClaimTemplates'][0]
                    # deployment_pvc['spec']['resources']['requests']['storage'] = resources_limits['disk']
                    # worker_class_sts['spec']['volumeClaimTemplates'][0] = add_common_labels(
                    #     common_labels=self.config.kube_common_labels(),
                    #     resource=deployment_pvc
                    # )
                    # append to the resource list
                    deployments.append(worker_class_sts)
                elif KubeResource(resource['kind']) == KubeResource.SERVICE:
                    # Prepare worker PVC
                    worker_class_svc = deepcopy(resource)
                    worker_class_svc['metadata']['name'] = svc_name
                    worker_class_svc['metadata']['labels']['app.kubernetes.io/name'] = svc_name
                    worker_class_svc['spec']['selector']['app.kubernetes.io/name'] = sts_name
                    # append to the resource list
                    deployments.append(worker_class_svc)
                else:
                    # Others
                    pass

        return deployments

    def _create_kubernetes_resources(self, result: StepResult,
                                     kube_resources,
                                     delete_if_exists=True,
                                     wait_running=True,
                                     deployment_kind=KubeResource.DEPLOYMENT):
        kube_resources = sort_resources(kube_resources)
        if delete_if_exists is True:
            for resource in kube_resources:
                self.logger.info('Checking if {} "{}" exists in order to delete it'
                                 .format(KubeResource(resource['kind']).value, resource['metadata']['name']))
                delete_resource(
                    kind=KubeResource(resource['kind']),
                    name=resource['metadata']['name'],
                    namespace=self.config.kube_namespace(),
                    logger=self.logger,
                    wait=True,
                    timeout=120
                )

        async_threads = []
        for resource in kube_resources:
            resource = add_common_labels(self.config.kube_common_labels(), resource)
            self._add_resource_to_kubernetes_deployed_resources(
                kind=KubeResource(resource['kind']),
                name=resource['metadata']['name'])
            self.logger.debug('Scheduling creation of {}: {} with body: {}'
                              .format(KubeResource(resource['kind']).value, resource['metadata']['name'], resource))
            async_threads.append(apply_resource(
                body=resource,
                namespace=self.config.kube_namespace(),
                logger=self.logger,
                replace_if_exists=True,
                async_req=True
            ))
            self.logger.info('Scheduled creation of {}: "{}"'.format(KubeResource(resource['kind']).value,
                                                                     resource['metadata']['name']))
        self.logger.info('The creation of all the resources have been scheduled')

        res: MethodResult = handle_async_requests(async_threads, logger=self.logger)
        if res.success is False:
            result.success = False
            result.reason = res.reason if res.reason is not None else "SUCCESS"
            result.trace = res.trace
            return result
        else:
            self.logger.info('All the scheduled resources for step "{}" have been created'.format(result.step))

        if wait_running is True:
            deployments_to_wait = [dep for dep in kube_resources
                                   if KubeResource(dep['kind']) == KubeResource.DEPLOYMENT
                                   or KubeResource(dep['kind']) == KubeResource.STATEFUL_SET]
            for deployment in deployments_to_wait:
                self.logger.info('Waiting for the {} "{}" to be ready'
                                 .format(KubeResource(deployment['kind']).value,
                                         deployment['metadata']['name']))
                res = wait_for_resource_running(
                    kind=KubeResource(deployment['kind']),
                    name=deployment['metadata']['name'],
                    namespace=self.config.kube_namespace(),
                    timeout=300,
                    sleep=1,
                    log_interval=5,
                    logger=self.logger
                )

        result.from_method_result(res)
        return result

    def _add_resource_to_kubernetes_deployed_resources(self, kind, name):
        kind_list = self.kubernetes_deployed_resources[kind]
        if name not in kind_list:
            self.kubernetes_deployed_resources[kind].append(name)

    def _set_custom_image_version(self, resource):
        if KubeResource(resource['kind']) == KubeResource.DEPLOYMENT or \
                KubeResource(resource['kind']) == KubeResource.STATEFUL_SET:
            containers = resource['spec']['template']['spec']['containers']
            for container in containers:
                image = container['image']
                if image in self.config.custom_images():
                    container['image'] = f'{image}:{self.config.kube_image_version()}'

    @staticmethod
    def _verify_step(step_result: StepResult):
        if step_result.success is True:
            return True
        else:
            raise DeployStepException(step=step_result.step, reason=step_result.reason, trace=step_result.trace)
