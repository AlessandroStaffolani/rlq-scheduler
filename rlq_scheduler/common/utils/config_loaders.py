import yaml
import os
import argparse

from rlq_scheduler.common.utils.filesystem import ROOT_DIR


def load_yaml_config(config_file_path):
    """
    Load from path a yml file
    Parameters
    ----------
    config_file_path: str
        file path
    Returns
    -------
        a dict with the yml file structure
    """
    with open(config_file_path, 'rt') as f:
        config = yaml.safe_load(f.read())
        return config


def load_multiple_yamls_from_file(filepath):
    with open(filepath, 'rt') as file:
        return yaml.safe_load_all(file.read())


def load_app_config(config_file_path):
    config = load_yaml_config(config_file_path=config_file_path)
    global_config = config['global']
    for key, conf in config.items():
        if key != 'global':
            for k, c in global_config.items():
                config[key][k] = c
    return config


def parse_arguments(title='Service Broker Celery', default_args=None):
    parser = argparse.ArgumentParser(description=title)
    parser.add_argument('--config-path', default=default_args['CONFIG_PATH'],
                        help='Configuration file path. Default: {}'.format(default_args['CONFIG_PATH']))
    parser.add_argument('--log-config-path', default=default_args['LOG_CONFIG_PATH'],
                        help='Log configuration file path. Default: {}'.format(default_args['LOG_CONFIG_PATH']))
    parser.add_argument('--clean-logs', action="store_true", default=default_args['CLEAN_LOGS'],
                        help='If present the logs folder will be cleaned before starting')
    return parser.parse_args()


def load_global_config(global_config, config_path):
    if global_config is None:
        if not os.path.isabs(config_path):
            config_path = os.path.join(ROOT_DIR, config_path)
        if os.path.exists(config_path):
            global_config = load_yaml_config(config_path)
        else:
            raise AttributeError('Global config path not exist')
        return global_config
    else:
        return global_config
