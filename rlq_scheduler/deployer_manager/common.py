from enum import Enum
from kubernetes import client

from rlq_scheduler.common.exceptions import KubeMapperMethodException


class DeploymentStatus(str, Enum):
    NOT_INITIALIZED = 'NOT_INITIALIZED'
    DEPLOYING = 'DEPLOYING'
    READY = 'READY'
    CLEANING = 'CLEANING'
    ERROR = 'ERROR'


class KubeResource(str, Enum):
    NAMESPACE = 'Namespace'
    CONFIG_MAP = 'ConfigMap'
    SECRET = 'Secret'
    DEPLOYMENT = 'Deployment'
    STATEFUL_SET = 'StatefulSet'
    DAEMON_SET = 'DaemonSet'
    SERVICE = 'Service'
    PERSISTENT_VOLUME_CLAIM = 'PersistentVolumeClaim'
    SERVICE_ACCOUNT = 'ServiceAccount'
    CLUSTER_ROLE = 'ClusterRole'
    CLUSTER_ROLE_BINDING = 'ClusterRoleBinding'


RESOURCE_KIND_MAPPER = {
    KubeResource.NAMESPACE: {
        'client': client.CoreV1Api,
        'read': 'read_namespace',
        'create': 'create_namespace',
        'delete': 'delete_namespace',
        'list': None,
        'delete_many': None
    },
    KubeResource.CONFIG_MAP: {
        'client': client.CoreV1Api,
        'read': 'read_namespaced_config_map',
        'create': 'create_namespaced_config_map',
        'delete': 'delete_namespaced_config_map',
        'list': 'list_namespaced_config_map',
        'delete_many': 'delete_collection_namespaced_config_map'
    },
    KubeResource.SERVICE: {
        'client': client.CoreV1Api,
        'read': 'read_namespaced_service',
        'create': 'create_namespaced_service',
        'delete': 'delete_namespaced_service',
        'list': 'list_namespaced_service',
        'delete_many': None
    },
    KubeResource.SECRET: {
        'client': client.CoreV1Api,
        'read': 'read_namespaced_secret',
        'create': 'create_namespaced_secret',
        'delete': 'delete_namespaced_secret',
        'list': 'list_namespaced_secret',
        'delete_many': 'delete_collection_namespaced_secret'
    },
    KubeResource.PERSISTENT_VOLUME_CLAIM: {
        'client': client.CoreV1Api,
        'read': 'read_namespaced_persistent_volume_claim',
        'create': 'create_namespaced_persistent_volume_claim',
        'delete': 'delete_namespaced_persistent_volume_claim',
        'list': 'list_namespaced_persistent_volume_claim',
        'delete_many': 'delete_collection_namespaced_persistent_volume_claim'
    },
    KubeResource.DEPLOYMENT: {
        'client': client.AppsV1Api,
        'read': 'read_namespaced_deployment',
        'create': 'create_namespaced_deployment',
        'delete': 'delete_namespaced_deployment',
        'list': 'list_namespaced_deployment',
        'delete_many': 'delete_collection_namespaced_deployment'
    },
    KubeResource.STATEFUL_SET: {
        'client': client.AppsV1Api,
        'read': 'read_namespaced_stateful_set',
        'create': 'create_namespaced_stateful_set',
        'delete': 'delete_namespaced_stateful_set',
        'list': 'list_namespaced_stateful_set',
        'delete_many': 'delete_collection_namespaced_stateful_set'
    },
    KubeResource.DAEMON_SET: {
        'client': client.AppsV1Api,
        'read': 'read_namespaced_daemon_set',
        'create': 'create_namespaced_daemon_set',
        'delete': 'delete_namespaced_daemon_set',
        'list': 'list_namespaced_daemon_set',
        'delete_many': 'delete_collection_namespaced_daemon_set'
    },
    KubeResource.SERVICE_ACCOUNT: {
        'client': client.CoreV1Api,
        'read': 'read_namespaced_service_account',
        'create': 'create_namespaced_service_account',
        'delete': 'delete_namespaced_service_account',
        'list': 'list_namespaced_service_account',
        'delete_many': 'delete_collection_namespaced_service_account'
    },
    KubeResource.CLUSTER_ROLE: {

    },
    KubeResource.CLUSTER_ROLE_BINDING: {

    }
}


class ResourceMapper:

    def __init__(self, kind: KubeResource):
        self.kind: KubeResource = kind
        self.mapper_options = RESOURCE_KIND_MAPPER[kind]
        self.api_instance = self.mapper_options['client']()

    def read(self, name, **kwargs):
        if self.mapper_options['read'] is not None:
            return getattr(self.api_instance, self.mapper_options['read'])(name=name, **kwargs)
        else:
            raise KubeMapperMethodException(method='read', kind=self.kind.value)

    def create(self, body, **kwargs):
        if self.mapper_options['create'] is not None:
            return getattr(self.api_instance, self.mapper_options['create'])(body=body, **kwargs)
        else:
            raise KubeMapperMethodException(method='create', kind=self.kind.value)

    def delete(self, name, **kwargs):
        if self.mapper_options['delete'] is not None:
            return getattr(self.api_instance, self.mapper_options['delete'])(name=name, **kwargs)
        else:
            raise KubeMapperMethodException(method='delete', kind=self.kind.value)

    def list(self, label_selector, **kwargs):
        if self.mapper_options['list'] is not None:
            method = getattr(self.api_instance, self.mapper_options['list'])
            return method(label_selector=label_selector, **kwargs)
        else:
            raise KubeMapperMethodException(method='list', kind=self.kind.value)

    def delete_many(self, label_selector, **kwargs):
        if self.mapper_options['delete_many'] is not None:
            method = getattr(self.api_instance, self.mapper_options['delete_many'])
            return method(label_selector=label_selector, **kwargs)
        else:
            raise KubeMapperMethodException(method='delete_many', kind=self.kind.value)


class MethodResult:

    def __init__(self, success, reason=None, trace=None, value=None):
        self.success = success
        self.reason = reason
        self.trace = trace
        self.value = value

    def to_dict(self):
        return {
            'success': self.success,
            'reason': self.reason,
            'trace': self.trace
        }


class StepResult(MethodResult):

    def __init__(self, step, success, reason=None, trace=None, value=None):
        super(StepResult, self).__init__(success=success, reason=reason, trace=trace, value=value)
        self.step = step

    def from_method_result(self, res: MethodResult):
        self.success = res.success
        self.reason = res.reason if res.reason is not None else "SUCCESS"
        self.trace = res.trace

    def to_dict(self):
        return {
            'step': self.step,
            'success': self.success,
            'reason': self.reason,
            'trace': self.trace
        }


class ActionResult(MethodResult):

    def __init__(self, action, success, reason=None, trace=None, extras=None, value=None):
        super(ActionResult, self).__init__(success, reason, trace=trace, value=value)
        self.action = action
        self.extras = extras if extras is not None else {}

    def to_dict(self):
        return {
            'step': self.action,
            'success': self.success,
            'reason': self.reason,
            'trace': self.trace,
            'extras': self.extras
        }


def label_to_label_selector(label):
    label_selector = label
    label_key = list(label_selector.keys())[0]
    label_value = list(label_selector.values())[0]
    return f'{label_key}={label_value}'
