from logging import Logger

import numpy as np

from rlq_scheduler.common.config_helper import MultiRunConfigHelper, SystemManagerConfigHelper, GlobalConfigHelper
from rlq_scheduler.common.run_config import RunConfig
from rlq_scheduler.common.system_events.producer import SystemEventProducer
from rlq_scheduler.common.system_status import SystemStatus
from rlq_scheduler.common.utils.filesystem import get_absolute_path
from rlq_scheduler.common.run_config_generator import prepare_runs_config, \
    prepare_runs_random_seeds
from rlq_scheduler.system_manager.system_manager import SystemManager


class RunManager:

    def __init__(self,
                 config: MultiRunConfigHelper,
                 system_manager_config: SystemManagerConfigHelper,
                 global_config: GlobalConfigHelper,
                 system_producer: SystemEventProducer,
                 system_manager: SystemManager,
                 config_folder='config',
                 logger: Logger = None
                 ):
        self.name = 'RunManager'
        self.config: MultiRunConfigHelper = config
        self.system_manager_config: SystemManagerConfigHelper = system_manager_config
        self.global_config: GlobalConfigHelper = global_config
        self.logger: Logger = logger
        self.is_auto_start = self.system_manager_config.is_auto_start()
        self.is_auto_run = self.system_manager_config.is_auto_run()
        self.config_folder = get_absolute_path(config_folder)
        self.system_producer: SystemEventProducer = system_producer
        self.system_manager: SystemManager = system_manager
        self.random = np.random.RandomState(self.config.global_seed())
        self.is_first_run = True
        self.runs_config_to_execute = []
        self.current_run = None
        self.current_run_started = False
        self.current_tasks_to_execute = None
        self.current_tasks_executed = None
        self.is_current_execution_completed = True
        self.executed_runs = []
        self.seeds = {
            'task_generator': None,
            'agent': []
        }
        self.is_running = False

    def should_prepare_runs_config(self):
        should = True
        if self.config.auto_generate_seeds() is True and self.config.n_runs() == 0:
            should = False
        elif self.config.auto_generate_seeds() is False and len(self.config.agent_seeds()) == 0:
            should = False
        return should

    def prepare_initial_runs_config(self):
        if self.should_prepare_runs_config():
            self.seeds = prepare_runs_random_seeds(random_generator=self.random,
                                                   multi_run_config=self.config)
            self.logger.info('Generated seeds for the runs random generators. Seeds = {}'.format(self.seeds),
                             resource='ResourceManager')
            self.runs_config_to_execute = prepare_runs_config(
                seeds=self.seeds,
                multi_run_config=self.config,
                config_folder=self.config_folder
            )
            self.logger.info('Initial runs configuration ready. Run to executes = {}'
                             .format(len(self.runs_config_to_execute)), resource='ResourceManager')
            real_runs_to_execute = []
            for index, conf in enumerate(self.runs_config_to_execute):
                if index < self.system_manager_config.start_from():
                    self.executed_runs.append(conf)
                else:
                    real_runs_to_execute.append(conf)
                self.logger.debug(conf)
            self.runs_config_to_execute = real_runs_to_execute
            self.logger.info('Initial runs configuration ready. Run to executes = {} | '
                             'Run executed = {} | Start from: {}'
                             .format(len(self.runs_config_to_execute),
                                     len(self.executed_runs),
                                     self.system_manager_config.start_from()), resource='ResourceManager')
        else:
            self.logger.info('No runs config have been generated', resource='ResourceManager')

    def start(self):
        try:
            self.logger.info('{} is starting to prepare runs configuration'.format(self.name),
                             resource='ResourceManager')
            self.prepare_initial_runs_config()
            self.is_running = True
        except Exception as e:
            self.logger.exception(e)

    def stop(self):
        try:
            self.is_running = False
            self.logger.info('{} has been stopped'.format(self.name), resource='ResourceManager')
        except Exception as e:
            self.logger.exception(e)

    def system_changed_status(self, system_status: SystemStatus):
        if system_status == SystemStatus.NOT_READY:
            self.logger.debug('{} waiting for system to in the WAITING state'.format(self.name),
                              resource='ResourceManager')
            return
        if system_status == SystemStatus.WAITING:
            # the system is in waiting status, so we can prepare the configuration for the next run
            self.prepare_next_run()
        if system_status == SystemStatus.READY:
            # all the resources have prepared their configuration for the new run, we can start it
            self.start_next_run()
        if system_status == SystemStatus.RUNNING:
            # the system has started the execution
            pass
        if system_status == SystemStatus.STOPPED:
            # the system goes in teh STOPPED status
            self.logger.warning('The system is in STOPPED state. It is required to restart the resources',
                                resource='ResourceManager')
        if system_status == SystemStatus.ERROR:
            # an fatal error occurred
            self.logger.error('The system is in ERROR state. It is required a manual intervention',
                              resource='ResourceManager')

    def prepare_next_run(self):
        if self.is_first_run:
            if self.is_auto_start:
                # if we are at the first run and we want to auto start, then schedule the run
                self.schedule_next_run()
        else:
            if self.is_auto_run:
                # it is not the first run, but we want to run all the configurations autonomously
                self.schedule_next_run()

    def start_next_run(self):
        if self.system_manager.system_status == SystemStatus.READY and self.current_run_started is False:
            self.logger.info('Starting the execution of the new run with code: {} and config: {}'
                             .format(self.current_run.run_code, self.current_run.config),
                             resource='ResourceManager')
            self.system_producer.publish_start_run_event(run_code=self.current_run.run_code)
            self.current_run_started = True
        else:
            self.logger.warning('Unable to start the new run, because current system status = {}'
                                .format(self.system_manager.system_status), resource='ResourceManager')

    def schedule_next_run(self):
        try:
            if self.system_manager.system_status == SystemStatus.WAITING \
                    and self.is_current_execution_completed is True:
                self.current_run: RunConfig = self.runs_config_to_execute.pop(0)
                self.current_run_started = False
                self.is_current_execution_completed = False
                self.logger.info('Preparing run number {} with code: {} and config {}. Remaining runs {}'
                                 .format(len(self.executed_runs) + 1,
                                         self.current_run.run_code,
                                         self.current_run.config,
                                         len(self.runs_config_to_execute)
                                         ), resource='ResourceManager')
                self.system_producer.publish_prepare_new_run_event(self.current_run)
                if self.is_first_run is True:
                    self.is_first_run = False
                return True
            else:
                self.logger.warning('Unable to schedule the new run, because current system status = {}'
                                    .format(self.system_manager.system_status), resource='ResourceManager')
                return False
        except IndexError:
            self.logger.info('No more runs to execute', resource='ResourceManager')
            return False

    def add_run_to_execute(self, run_config: RunConfig or list):
        if isinstance(run_config, list):
            self.runs_config_to_execute.extend(run_config)
        else:
            self.runs_config_to_execute.append(run_config)
