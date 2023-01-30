from rlq_scheduler.common.config_helper import GlobalConfigHelper


def prepare_url(config_key, global_config: GlobalConfigHelper, use_kube_port=False, host=None):
    if global_config is not None:
        api_config = global_config.api_resource_endpoint(config_key)
        protocol = api_config['protocol']
        host = api_config['host'] if host is None else host
        port = api_config['port'] if use_kube_port is False else api_config['kube_port']
        return f'{protocol}://{host}:{port}'
    else:
        raise AttributeError('Config object is not initialized')