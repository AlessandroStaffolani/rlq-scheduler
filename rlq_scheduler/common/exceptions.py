

class ConfigException(Exception):

    def __init__(self, message='Configuration error, the following properties are wrong or missing', fields=None, *args):
        self.full_message = message
        if fields is not None and len(fields) > 0:
            self.full_message += ':\n'
            for field in fields:
                self.full_message += '\t' + str(field) + '\n'
        super(ConfigException, self).__init__(self.full_message, *args)


class NoRunConfigException(Exception):

    def __init__(self, component_name=None, *args):
        message = 'No run config provided'
        if component_name is not None:
            message += f' for component: {component_name}'
        super(NoRunConfigException, self).__init__(message, *args)


class NoStateFoundForTrajectoryException(Exception):

    def __init__(self, trajectory_id, *args):
        message = 'No state has been generated for trajectory {}'.format(trajectory_id)
        super(NoStateFoundForTrajectoryException, self).__init__(message, *args)


class CeleryNotReachable(Exception):

    def __init__(self, *args):
        message = 'Celery is not reachable'
        super(CeleryNotReachable, self).__init__(message, *args)


class DeployStepException(Exception):

    def __init__(self, step, reason, trace=None, *args):
        message = 'Error during the deployment of step: "{}". Reason: "{}". Error trace: {}'.format(step, reason, trace)
        super(DeployStepException, self).__init__(message, *args)


class KubeMapperMethodException(Exception):

    def __init__(self, method, kind, *args):
        message = 'Method {} for kind "{}" not available in Kubernetes ResourceMapper'.format(method, kind)
        super(KubeMapperMethodException, self).__init__(message, *args)
