import argparse

from rlq_scheduler.task_generator.server import create_server

DEFAULT_ARGS = {
    'CONFIG_PATH': 'config/task_generator.yml',
    'GLOBAL_CONFIG_PATH': 'config/global.yml'
}


def parse_arguments():
    parser = argparse.ArgumentParser(description='Task Generator')
    parser.add_argument('--config-path', default=DEFAULT_ARGS['CONFIG_PATH'],
                        help='Configuration file path. Default: {}'.format(DEFAULT_ARGS['CONFIG_PATH']))
    parser.add_argument('--global-config-path', default=DEFAULT_ARGS['GLOBAL_CONFIG_PATH'],
                        help='Global configuration file path. Default: {}'.format(DEFAULT_ARGS['GLOBAL_CONFIG_PATH']))
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_arguments()
    server = create_server(args.config_path, args.global_config_path)
    server.run(host='0.0.0.0', port=9093, debug=False)
