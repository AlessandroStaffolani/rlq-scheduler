import argparse

from rlq_scheduler.trajectory_collector.server import create_server

DEFAULT_ARGS = {
    'CONFIG_PATH': 'config/trajectory_collector.yml',
    'GLOBAL_CONFIG_PATH': 'config/global.yml'
}


def parse_arguments():
    parser = argparse.ArgumentParser(description='Trajectory Collector')
    parser.add_argument('--config-path', default=DEFAULT_ARGS['CONFIG_PATH'],
                        help='Configuration file path. Default: {}'.format(DEFAULT_ARGS['CONFIG_PATH']))
    parser.add_argument('--global-config-path', default=DEFAULT_ARGS['GLOBAL_CONFIG_PATH'],
                        help='Global configuration file path. Default: {}'.format(DEFAULT_ARGS['GLOBAL_CONFIG_PATH']))
    return parser.parse_args()


if __name__ == '__main__':
    # get parameters and config
    args = parse_arguments()
    server = create_server(args.config_path, args.global_config_path)
    server.run(host='0.0.0.0', port=9091, debug=False)
