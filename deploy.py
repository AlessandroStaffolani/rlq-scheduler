import argparse
import logging
import os
import time
from copy import deepcopy
from multiprocessing.pool import ThreadPool

from rlq_scheduler.common.config_helper import GlobalConfigHelper, DeployerManagerConfigHelper
from rlq_scheduler.common.utils.filesystem import ROOT_DIR
from rlq_scheduler.common.utils.logger import get_logger
from rlq_scheduler.deployer_manager.common import ActionResult
from rlq_scheduler.deployer_manager.deployer_manager import DeployerManager

DEFAULT_ARGS = {
    'CONFIG_PATH': 'config/deployer_manager.yml',
    'GLOBAL_CONFIG_PATH': 'config/global.yml',
    'DEPLOYMENT_FOLDER': 'config/deployments',
    'LOGGING_LEVEL': logging.DEBUG,
    'SLEEP': 10,
}


AGENTS_FOLDERS = [
    'execution-time',
    'execution-cost',
    'waiting-time',
]

DEPLOYMENT_FILENAME = 'deployer_manager.yml'


def parse_arguments():
    parser = argparse.ArgumentParser(description='DeployerManager')
    parser.add_argument('--all', dest='all', action='store_true',
                        help='Deploy all the deployments present in the deployment folder')
    parser.add_argument('--config-path', default=DEFAULT_ARGS['CONFIG_PATH'],
                        help='Configuration file path. Default: {}'.format(DEFAULT_ARGS['CONFIG_PATH']))
    parser.add_argument('--global-config-path', default=DEFAULT_ARGS['GLOBAL_CONFIG_PATH'],
                        help='Global configuration file path. Default: {}'.format(DEFAULT_ARGS['GLOBAL_CONFIG_PATH']))
    parser.add_argument('--folder', default=DEFAULT_ARGS['DEPLOYMENT_FOLDER'],
                        help='Folder used to load deployments files when all mode is enabled. Default {}'
                        .format(DEFAULT_ARGS['DEPLOYMENT_FOLDER']))
    parser.add_argument('-l', '--level', type=int, default=DEFAULT_ARGS['LOGGING_LEVEL'],
                        help='Logging level for the script. Default: {}. Options: [10, 20, 30, 40] '
                             'where 10 is DEBUG and 40 is ERROR'.
                        format(DEFAULT_ARGS['LOGGING_LEVEL']))
    parser.add_argument('--sleep', type=int, default=DEFAULT_ARGS['SLEEP'],
                        help='Sleeping seconds between each action in all mode. Default: {}'
                        .format(DEFAULT_ARGS['SLEEP']))
    parser.add_argument('action', type=str.lower, choices=['deploy', 'cleanup', 'status'],
                        help='Chose the action to perform on the deployment. '
                             'Available are ["deploy", "cleanup", "status"]')
    return parser.parse_args()


def deploy_action(dm: DeployerManager) -> ActionResult:
    return dm.deploy()


def cleanup_action(dm: DeployerManager) -> ActionResult:
    return dm.clean_up()


def status_action(dm: DeployerManager) -> ActionResult:
    result = ActionResult(success=True, reason='SUCCESS', action="ServiceBroker system status")
    return result


def all_action(folder: str, action: str, g_config: GlobalConfigHelper, log: logging.Logger, sleep=0):
    pool = ThreadPool(5)
    results = []
    for agent in AGENTS_FOLDERS:
        path = os.path.join(ROOT_DIR, folder, agent, DEPLOYMENT_FILENAME)
        if os.path.exists(path):
            log.info(f'Starting deployment for agent {agent}')
            dm = DeployerManager(
                config=DeployerManagerConfigHelper(config_path=path),
                global_config=g_config,
                logger=log,
                script_mode=True
            )
            if action == 'deploy':
                results.append({
                    'agent': agent,
                    'result': pool.apply_async(deploy_action, args=(dm, ))
                })
            elif action == 'cleanup':
                results.append({
                    'agent': agent,
                    'result': pool.apply_async(cleanup_action, args=(dm,))
                })
            else:
                raise AttributeError('Using --all parameter actions allowed are only: "deploy" and "cleanup"')
        else:
            log.error(f'No deployment file for agent {agent} at path {path}')
        log.info(f'Sleeping {sleep} seconds before scheduling next')
        time.sleep(sleep)
    log.info('All the deployments have been started')
    for res in results:
        res['result'].wait()
        log.info(f'Executed action {action} for agent deployment {res["agent"]} with success')
    log.info(f'Completed action {action} with SUCCESS')
    pool.close()
    pool.join()


if __name__ == '__main__':
    switcher = {
        'deploy': deploy_action,
        'cleanup': cleanup_action,
        'status': status_action
    }
    args = parse_arguments()
    global_config = GlobalConfigHelper(config_path=args.global_config_path)
    config = DeployerManagerConfigHelper(config_path=args.config_path)
    logger_config = config.logger()
    logger_config['level'] = args.level
    logger = get_logger(logger_config)
    logger.info('Running action: {} on the ServiceBroker deployment'.format(args.action))
    logger.info('Initializing DeployerManager')
    logger.info('Global config are: {}'.format(global_config))
    logger.info('DeployerManager config are: {}'.format(config))
    if args.all is True:
        all_action(args.folder, args.action, global_config, logger, sleep=args.sleep)
    else:
        deployer_manager: DeployerManager = DeployerManager(
            config=config,
            global_config=global_config,
            logger=logger,
            script_mode=True
        )
        if args.action in switcher:
            action_result: ActionResult = switcher[args.action](deployer_manager)
            if action_result.success is True:
                logger.info('Action {} completed with success. Result message: {}'
                            .format(args.action, action_result.reason))
            else:
                logger.error('Execution of action {} failed. Reason: {}. Error trace: {}'
                             .format(args.action, action_result.reason, action_result.trace))
        else:
            raise AttributeError('Action {} is not a valid action'.format(args.action))
