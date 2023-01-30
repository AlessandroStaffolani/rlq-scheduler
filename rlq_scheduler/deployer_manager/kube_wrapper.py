import logging
import time
import traceback
from functools import cmp_to_key
from threading import Thread

from kubernetes import client
from kubernetes.client.rest import ApiException

from rlq_scheduler.common.exceptions import KubeMapperMethodException
from rlq_scheduler.deployer_manager.common import MethodResult, KubeResource, ResourceMapper


def list_cluster_nodes(logger: logging.Logger):
    api = client.CoreV1Api()
    nodes = api.list_node(watch=False)
    logger.info('Kubernetes cluster nodes:')
    nodes_ip = []
    for n in nodes.items:
        status = n.status.conditions[-1].status
        node_ip = n.status.addresses[0].address
        nodes_ip.append(node_ip)
        if status == 'True':
            logger.info('Node: {} | Status: {} | Host: {} | Ip: {} | Role: {}'.format(
                n.metadata.name,
                'Ready',
                n.status.addresses[1].address,
                node_ip,
                'master' if 'node-role.kubernetes.io/master' in n.metadata.labels else 'worker'
            ))
        else:
            logger.warning('Node: {} | Status: {} | Host: {} | Ip: {} | Role: {}'.format(
                n.metadata.name,
                'Not Ready',
                n.status.addresses[1].address,
                node_ip,
                'master' if 'node-role.kubernetes.io/master' in n.metadata.labels else 'worker'
            ))
    return nodes_ip


def resource_exists(mapper: ResourceMapper, name: str, **kwargs):
    try:
        resource = mapper.read(name=name, **kwargs)
        return resource is not None
    except ApiException as api_error:
        if api_error.status == 404:
            return False
        else:
            raise api_error


def apply_resource(body: dict,
                   logger: logging.Logger = None,
                   replace_if_exists=False,
                   async_req=False,
                   **kwargs
                   ) -> MethodResult or Thread:
    """
    Apply a resource on kubernetes. The resource must be of kind support by KubeResource
    Parameters
    ----------
    body: dict
        body of the resource to apply
    namespace: str
        namespace in which creates the resource
    logger: logging.Logger or None
        logger
    replace_if_exists: bool
        if True and if the resource already exists it will be firstly removed and then created
    async_req: bool
        if True it doesn't wait for the end of the creation of the resource, instead it returns a Thread
    Returns
    -------
    MethodResult or Thread
        MethodResult object or Thread if async_req is True
    """
    try:
        kind = body['kind']
        resource_name = body['metadata']['name']
        resource_mapper = ResourceMapper(KubeResource(kind))
        exists = resource_exists(resource_mapper, name=resource_name, **kwargs)

        if exists is True and replace_if_exists is True:
            resource_mapper.delete(name=resource_name, **kwargs)
        elif exists is True and replace_if_exists is False:
            log_debug(logger, 'Resource of kind: {} with name: {} already exists'.format(kind, resource_name))

        if exists is False or (exists is True and replace_if_exists is True):
            if async_req is False:
                resource = resource_mapper.create(
                    body=body,
                    **kwargs
                )
                log_debug(logger, 'Created resource of kind: {} with name: {}'.format(kind, resource.metadata.name))
                return MethodResult(success=True)
            else:
                thread = resource_mapper.create(
                    body=body,
                    async_req=async_req,
                    **kwargs
                )
                return thread
        else:
            return MethodResult(success=True, reason='Resource of kind: {} with name: {} already exists'
                                .format(kind, resource_name))
    except KubeMapperMethodException as err:
        log_debug(logger, err)
    except ApiException as api_error:
        log_error(logger, api_error)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=api_error.reason, trace=traceback.format_exc())
    except Exception as e:
        log_error(logger, e)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=e, trace=traceback.format_exc())


def delete_resource(kind: KubeResource, name, namespace='default', logger: logging.Logger = None, wait=False,
                    timeout=60) -> MethodResult:
    try:
        resource_mapper = ResourceMapper(kind)
        exists = resource_exists(resource_mapper, name=name, namespace=namespace)
        if exists is True:
            resource_mapper.delete(name=name, namespace=namespace)

        if wait is True:
            return wait_for_resource_deletion(
                mapper=resource_mapper,
                name=name,
                namespace=namespace,
                timeout=timeout,
                logger=logger
            )
        return MethodResult(success=True)
    except ApiException as api_error:
        log_error(logger, api_error)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=api_error.reason, trace=traceback.format_exc())
    except Exception as e:
        log_error(logger, e)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=e, trace=traceback.format_exc())


def delete_many_resources(kind, label, namespace='default', logger: logging.Logger = None) -> MethodResult:
    try:
        resource_mapper = ResourceMapper(kind)
        resource_mapper.delete_many(label_selector=label, namespace=namespace)
    except ApiException as api_error:
        log_error(logger, api_error)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=api_error.reason, trace=traceback.format_exc())
    except Exception as e:
        log_error(logger, e)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=e, trace=traceback.format_exc())


def list_many_resources(kind, label, namespace='default', minimal_info=True,
                        logger: logging.Logger = None) -> MethodResult:
    try:
        resource_mapper = ResourceMapper(kind)
        resources = resource_mapper.list(label_selector=label, namespace=namespace)
        if minimal_info is True:
            resources_to_return = []
            for res in resources.items:
                name = res.metadata.name
                if resource_mapper.kind == KubeResource.DAEMON_SET or resource_mapper.kind == KubeResource.DEPLOYMENT \
                        or resource_mapper.kind == KubeResource.STATEFUL_SET:
                    is_running = is_resource_running(
                        resource_mapper,
                        name=name,
                        namespace=namespace,
                        logger=logger).success
                    if is_running is True:
                        resources_to_return.append(name)
                else:
                    resources_to_return.append(name)
            return MethodResult(success=True, reason='SUCCESS', value=resources_to_return)
        else:
            return MethodResult(success=True, reason='SUCCESS', value=resources)
    except ApiException as api_error:
        log_error(logger, api_error)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=api_error.reason, trace=traceback.format_exc())
    except Exception as e:
        log_error(logger, e)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=e, trace=traceback.format_exc())


def wait_for_resource_deletion(mapper: ResourceMapper, name, namespace='default', timeout=60,
                               sleep=1, log_interval=2, logger=None):
    try:
        countdown = timeout
        while countdown > 0:
            mapper.read(name=name, namespace=namespace)
            countdown -= sleep
            if countdown % log_interval == 0:
                log_debug(logger, 'Waiting for the deletion of {} "{}"'.format(mapper.kind.value, name))
            time.sleep(sleep)
        return MethodResult(success=False, reason='Timeout error')
    except ApiException as api_error:
        if api_error.status == 404:
            return MethodResult(success=True)
        else:
            log_error(logger, api_error)
            log_debug(logger, traceback.format_exc())
            return MethodResult(success=False, reason=api_error.reason, trace=traceback.format_exc())
    except Exception as e:
        log_error(logger, e)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=e, trace=traceback.format_exc())


def is_resource_running(mapper: ResourceMapper, name, namespace='default', logger=None):
    try:
        res = mapper.read(name=name, namespace=namespace)
        if mapper.kind == KubeResource.DEPLOYMENT or mapper.kind == KubeResource.STATEFUL_SET:
            if res.status.ready_replicas == res.status.replicas:
                return MethodResult(success=True)
            else:
                return MethodResult(success=False, reason='Not running')
        elif mapper.kind == KubeResource.DAEMON_SET:
            if res.status.current_number_scheduled == res.status.desired_number_scheduled:
                return MethodResult(success=True)
            else:
                return MethodResult(success=False, reason='Not running')
        else:
            return MethodResult(success=False, reason='Resource kind not "Deployment", "StatefulSet" or "DaemonSet"')
    except ApiException as api_error:
        log_error(logger, api_error)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=api_error.reason, trace=traceback.format_exc())
    except Exception as e:
        log_error(logger, e)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=e, trace=traceback.format_exc())


def wait_for_resource_running(kind: KubeResource, name, namespace='default', timeout=60, sleep=1,
                              log_interval=2, logger=None):
    try:
        countdown = timeout
        mapper = ResourceMapper(kind)
        while countdown > 0:
            res = is_resource_running(mapper, name, namespace, logger)
            if res.success:
                # resource is running
                return MethodResult(success=True)
            if countdown % log_interval == 0:
                log_debug(logger, 'Waiting for the {} "{}" to be ready'.format(mapper.kind.value, name))
            countdown -= sleep
            time.sleep(sleep)

        return MethodResult(success=False, reason='Timeout error')
    except ApiException as api_error:
        if api_error.status == 404:
            return MethodResult(success=False, reason='Resource not found', trace=traceback.format_exc())
        else:
            log_error(logger, api_error)
            log_debug(logger, traceback.format_exc())
            return MethodResult(success=False, reason=api_error.reason, trace=traceback.format_exc())
    except Exception as e:
        log_error(logger, e)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=e, trace=traceback.format_exc())


def update_deployment_env_variable(body, env_name, env_value, logger) -> MethodResult:
    try:
        n_updates = 0
        containers = body['spec']['template']['spec']['containers']
        for container in containers:
            if 'env' in container:
                env_variables = container['env']
                for env in env_variables:
                    if env['name'] == env_name:
                        env['value'] = env_value
                        n_updates += 1
        if n_updates > 0:
            return MethodResult(success=True, reason='Env: {} updated {} times with value: {}. Resource name: {}'
                                .format(env_name, n_updates, env_value, body['metadata']['name']))
        else:
            return MethodResult(success=True, reason='Env name: {} is not present in the deployment with name: {}'
                                .format(env_name, body['metadata']['name']))
    except Exception as e:
        log_error(logger, e)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=e, trace=traceback.format_exc())


def handle_async_requests(async_request: list, timeout=60, logger=None) -> MethodResult:
    try:
        for i, t in enumerate(async_request):
            _ = t.get(timeout=timeout)
            log_debug(logger, 'Handled {}/{} requests'.format(i + 1, len(async_request)))
        return MethodResult(success=True)
    except ApiException as api_error:
        log_error(logger, api_error)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=api_error.reason, trace=traceback.format_exc())
    except Exception as e:
        log_exception(logger, e)
        log_debug(logger, traceback.format_exc())
        return MethodResult(success=False, reason=e, trace=traceback.format_exc())


def sort_resources(resources_generator):
    resources_list = [r for r in resources_generator]
    kube_resources_order = list(KubeResource.__members__.keys())
    return sorted(resources_list, key=cmp_to_key(
        lambda r1, r2:
        kube_resources_order.index(KubeResource(r1['kind']).name) -
        kube_resources_order.index(KubeResource(r2['kind']).name)))


def get_deployment_resource_index(resources_list):
    deploy_resource_kinds = [KubeResource.DEPLOYMENT, KubeResource.STATEFUL_SET, KubeResource.DAEMON_SET]
    for i, res in enumerate(resources_list):
        kind = KubeResource(res['kind'])
        if kind in deploy_resource_kinds:
            return i
    return None


def add_common_labels(common_labels, resource):
    for label_dict in common_labels:
        label = list(label_dict.keys())[0]
        resource['metadata']['labels'][label] = label_dict[label]
    return resource


def log_debug(logger: logging.Logger, message):
    if logger is not None:
        logger.debug(message)


def log_info(logger: logging.Logger, message):
    if logger is not None:
        logger.info(message)


def log_warning(logger: logging.Logger, message):
    if logger is not None:
        logger.warning(message)


def log_error(logger: logging.Logger, message):
    if logger is not None:
        logger.error(message)


def log_exception(logger: logging.Logger, message):
    if logger is not None:
        logger.exception(message)
