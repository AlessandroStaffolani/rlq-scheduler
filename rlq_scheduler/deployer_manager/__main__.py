import argparse

from rlq_scheduler.deployer_manager.server import create_server

DEFAULT_ARGS = {
    'CONFIG_PATH': 'config/kube/deployer_manager.yml',
    'GLOBAL_CONFIG_PATH': 'config/kube/global.yml'
}


def parse_arguments():
    parser = argparse.ArgumentParser(description='DeployerManager')
    parser.add_argument('--config-path', default=DEFAULT_ARGS['CONFIG_PATH'],
                        help='Configuration file path. Default: {}'.format(DEFAULT_ARGS['CONFIG_PATH']))
    parser.add_argument('--global-config-path', default=DEFAULT_ARGS['GLOBAL_CONFIG_PATH'],
                        help='Global configuration file path. Default: {}'.format(DEFAULT_ARGS['GLOBAL_CONFIG_PATH']))
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_arguments()
    server = create_server(args.config_path, args.global_config_path)
    server.run(host='0.0.0.0', port=9093, debug=False)
