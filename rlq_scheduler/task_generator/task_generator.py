import json
import time

import numpy as np

from rlq_scheduler.common.config_helper import GlobalConfigHelper, TaskGeneratorConfigHelper, RunConfigHelper
from rlq_scheduler.common.system_events.event import RunPhase
from rlq_scheduler.common.system_events.producer import SystemEventProducer
from rlq_scheduler.common.trajectory_saver.saver import Saver
from rlq_scheduler.common.utils.filesystem import get_absolute_path
from rlq_scheduler.common.utils.logger import get_logger
from rlq_scheduler.task_generator.tasks_generation_distribution import task_generation_events, \
    generate_events_google_traces
from rlq_scheduler.tasks.task_broker import task_broker


class TaskGenerator:

    def __init__(self,
                 config: TaskGeneratorConfigHelper,
                 global_config: GlobalConfigHelper,
                 system_producer: SystemEventProducer,
                 trajectory_saver: Saver,
                 logger=None,
                 test_mode=False
                 ):
        self.name = 'TaskGenerator'
        self._test_mode = test_mode
        self.test_waiting_time_history = []
        self.scheduled_task_stats = {}
        self.config: TaskGeneratorConfigHelper = config
        self.global_config: GlobalConfigHelper = global_config
        self.run_config: RunConfigHelper = None
        self.logger = logger if logger is not None else get_logger(self.config.logger())
        self.system_producer: SystemEventProducer = system_producer
        self.trajectory_saver: Saver = trajectory_saver
        self.random: np.random.RandomState = None
        self.tasks_scheduled = 0
        self.tasks_bootstrapped = 0
        self.generation_rates = None
        self.current_run_code = None
        self.eval_dataset = None
        self.synthetic_dataset = None
        self.task_broker_queue = self.global_config.task_broker_queue_name()
        self.is_ready = False

    def init_datasets(self):
        if self.run_config.is_google_traces_mode_enabled():
            with open(get_absolute_path(self.global_config.datasets_google_traces_eval_dataset_path()), 'r') as f:
                self.eval_dataset = json.load(f)
            with open(get_absolute_path(self.global_config.datasets_google_traces_synthetic_dataset_path()), 'r') as f:
                self.synthetic_dataset = json.load(f)

    def _generate_task_create_events(self, gen_round):
        if self.run_config is not None:
            events, rates = task_generation_events(
                distribution=self.run_config.tasks_generation_distribution(gen_round),
                tasks_to_generate=self.run_config.tasks_to_generate_number_round(gen_round),
                rate_per_interval=self.run_config.tasks_rate_per_minute(gen_round),
                rate_per_interval_range=self.run_config.tasks_rate_per_interval_range(gen_round)
            )
            self.generation_rates = rates
            self.logger.debug('Generation rates are = {}'
                              .format(self.generation_rates if self.generation_rates is not None else 'no-rate'),
                              resource='TaskGenerator')
            return events
        else:
            raise AttributeError('RunConfig is None, cannot generate task create events')

    def _schedule_task(self):
        if self.run_config.is_google_traces_mode_enabled():
            return self._schedule_synthetic_task_from_google_traces()
        task_name = self.random.choice(self.run_config.available_tasks_classes())
        task_func_name = self.run_config.task_class_func_name(task_name)
        task_parameters = self.run_config.task_class_config(task_name)
        task_kwargs = {}
        for param, parameter_range in task_parameters.items():
            task_kwargs[param] = self.random.randint(parameter_range['min'], parameter_range['max'])
        task_kwargs['task_class'] = task_name
        return task_func_name, task_kwargs

    def _schedule_synthetic_task_from_google_traces(self):
        classes_frequencies = self.synthetic_dataset['task_classes']['frequencies']
        task_name = self.random.choice(self.run_config.available_tasks_classes(),
                           p=np.array(classes_frequencies)/np.sum(classes_frequencies))
        task_func_name = self.global_config.datasets_google_traces_task_function_name()
        time_of_execution = self.random.choice(self.synthetic_dataset['task_classes'][task_name]['tasks_durations'])
        time_of_execution *= self.run_config.google_traces_time_multiplier()
        task_kwargs = {
            'task_class': task_name,
            'time_of_execution': time_of_execution,
            'n': time_of_execution
        }
        return task_func_name, task_kwargs

    def _schedule_on_celery(self, task_func_name, task_kwargs, task_index, gen_round):
        self.logger.info('Generating task number {} with arguments: {}'
                         .format(task_index, {'name': task_func_name, 'args': task_kwargs}), resource='TaskGenerator')
        if self._test_mode is False:
            if task_index >= self.run_config.tasks_to_skip(gen_round):
                result = task_broker.apply_async(kwargs={
                    'name': task_func_name,
                    'parameters': task_kwargs
                }, queue=self.task_broker_queue)
                self.logger.debug('The generated task has uuid {}'.format(result.id), resource='TaskGenerator')
                self._store_stats(task_kwargs['task_class'])
                self._push_trajectory_task_info(
                    trajectory_id=result.id,
                    task_kwargs=task_kwargs
                )
            else:
                self.logger.debug('Skipped task number {}'.format(task_index), resource='TaskGenerator')
        self.tasks_scheduled += 1

    def _store_stats(self, task_name):
        if task_name not in self.scheduled_task_stats:
            self.scheduled_task_stats[task_name] = 1
        else:
            self.scheduled_task_stats[task_name] += 1

    def _schedule_on_celery_bootstrapping(self, task_index):
        task_func_name, task_kwargs = self._schedule_task()
        self.logger.info('Generating bootstrapping task number {} with arguments: {}'
                         .format(task_index, {'name': task_func_name, 'args': task_kwargs}), resource='TaskGenerator')
        if self._test_mode is False:
            if task_index >= self.run_config.tasks_bootstrapping_to_skip():
                result = task_broker.apply_async(kwargs={
                    'name': task_func_name,
                    'parameters': task_kwargs
                }, queue=self.task_broker_queue)
                self.logger.debug('Generated bootstrapping task with uuid {}'
                                  .format(result.id), resource='TaskGenerator')
                self._push_trajectory_task_info(
                    trajectory_id=result.id,
                    task_kwargs=task_kwargs
                )
            else:
                self.logger.debug('Skipped bootstrapping task number {}'.format(task_index), resource='TaskGenerator')
        self.tasks_bootstrapped += 1

    def _push_trajectory_task_info(self, trajectory_id, task_kwargs):
        if not self.trajectory_saver.disabled:
            task_class = task_kwargs['task_class']
            del task_kwargs['task_class']
            self.trajectory_saver.push_trajectory_extra(
                trajectory_id=trajectory_id,
                field='task_info',
                value={
                    'task_class': task_class,
                    'task_parameters': task_kwargs,
                }
            )

    def _generate_synthetic_google_traces_events(self, tasks_to_generate) -> tuple:
        i = 0
        events = np.array([])
        all_means = self.synthetic_dataset['events_means']
        while len(events) < tasks_to_generate:
            mean = all_means[i % len(all_means)]
            events = np.append(
                events,
                generate_events_google_traces(mean, mean, self.random, self.run_config.google_traces_time_multiplier())
            )
            i += 1
            self.logger.debug(f'Adding {mean} events', resource='TaskGenerator')
        events = events[:tasks_to_generate]
        self.logger.debug(f'Events generated {len(events)}, requested {tasks_to_generate} events',
                          resource='TaskGenerator')
        self.logger.debug(f'First event sleep time is: {events[0]} it is of type: {type(events[0])}')
        return events, None

    def schedule_bootstrapping_tasks(self):
        if self.run_config is not None:
            if self.run_config.is_bootstrapping_enabled():
                if self.run_config.tasks_bootstrapping_tasks_to_generate() > 0:
                    if self.run_config.is_google_traces_mode_enabled():
                        events, _ = self._generate_synthetic_google_traces_events(
                            self.run_config.tasks_bootstrapping_tasks_to_generate())
                    else:
                        events, _ = task_generation_events(
                            distribution=self.run_config.tasks_bootstrapping_generation_distribution(),
                            tasks_to_generate=self.run_config.tasks_bootstrapping_tasks_to_generate(),
                            rate_per_interval=self.run_config.tasks_bootstrapping_rate_interval(),
                            rate_per_interval_range=self.run_config.tasks_bootstrapping_rate_interval_range()
                        )
                    self.logger.info('Starting bootstrapping phase for {} tasks'
                                     .format(len(events)), resource='TaskGenerator')
                    self.system_producer.publish_scheduling_started_event(
                        phase=RunPhase.BOOTSTRAP,
                        task_to_generate=self.run_config.tasks_bootstrapping_tasks_to_generate(),
                        task_to_schedule_config=self.run_config.task_bootstrapping()
                    )
                    for i, sleep_time in enumerate(events):
                        self._schedule_on_celery_bootstrapping(i)
                        if self._test_mode is False:
                            time.sleep(sleep_time)
                    self.logger.info('All the bootstrapping tasks have been scheduled', resource='TaskGenerator')
                    self.system_producer.publish_scheduling_completed_event(
                        phase=RunPhase.BOOTSTRAP,
                        task_scheduled=self.tasks_bootstrapped)
            else:
                self.logger.info('Skipping bootstrapping phase')
        else:
            raise AttributeError('RunConfig is None, cannot schedule tasks')

    def schedule_tasks(self):
        if self.run_config is not None:
            self.logger.info('Starting scheduling tasks', resource='TaskGenerator')
            for round_i, task_to_generate_round in enumerate(self.run_config.tasks_to_generate()):
                self.logger.info('Generating {} tasks using distribution {} and rate {}'.format(
                        self.run_config.tasks_to_generate_number_round(round_i),
                        self.run_config.tasks_generation_distribution(round_i),
                        self.run_config.tasks_to_generate_round_rate(round_i)
                ))
                if self.run_config.is_google_traces_mode_enabled():
                    events, _ = self._generate_synthetic_google_traces_events(
                        self.run_config.tasks_to_generate_number_round(round_i))
                else:
                    events = self._generate_task_create_events(round_i)
                if round_i == 0:
                    # is first round, notify scheduling is started
                    self.system_producer.publish_scheduling_started_event(
                        phase=RunPhase.RUN,
                        task_to_generate=self.run_config.tasks_to_generate_total_number(),
                        task_to_schedule_config=self.run_config.tasks_to_generate()
                    )
                for i, sleep_time in enumerate(events):
                    task_func_name, task_kwargs = self._schedule_task()
                    self._schedule_on_celery(task_func_name, task_kwargs, i, round_i)
                    if self._test_mode is False:
                        time.sleep(sleep_time)
                    else:
                        self.test_waiting_time_history.append(sleep_time)
                self.logger.info('Generation round {} completed. '
                                 '{} tasks have been scheduled in this round for a total of {}'.format(
                                    round_i,
                                    len(events),
                                    self.tasks_scheduled), resource='TaskGenerator')
            self.logger.info('All the {} tasks for the run have been scheduled'.format(self.tasks_scheduled))
            self.system_producer.publish_scheduling_completed_event(
                phase=RunPhase.RUN,
                task_scheduled=self.tasks_scheduled)
        else:
            raise AttributeError('RunConfig is None, cannot schedule tasks')

    def schedule_eval_tasks(self):
        if self.run_config is not None:
            self.logger.info('Starting scheduling eval tasks', resource='TaskGenerator')
            tasks_to_generate = self.run_config.tasks_to_generate_number_round(0)
            if tasks_to_generate == -1 or tasks_to_generate > len(self.eval_dataset):
                tasks_to_generate = len(self.eval_dataset)
            self.logger.info('Generating {} eval tasks using google dataset at: {}'.format(
                tasks_to_generate, self.global_config.datasets_google_traces_eval_dataset_path()
            ))
            # notify scheduling is started
            self.system_producer.publish_scheduling_started_event(
                phase=RunPhase.RUN,
                task_to_generate=tasks_to_generate,
                task_to_schedule_config=self.run_config.tasks_to_generate()
            )
            for i in range(tasks_to_generate):
                task_func_name = self.global_config.datasets_google_traces_task_function_name()
                sleep_time = self.eval_dataset[str(i)]['next_task_start']
                sleep_time *= self.run_config.google_traces_time_multiplier()
                task_class = self.eval_dataset[str(i)]['task_class']
                time_of_execution = self.eval_dataset[str(i)]['duration']
                time_of_execution *= self.run_config.google_traces_time_multiplier()
                task_kwargs = {
                    'task_class': task_class,
                    'time_of_execution': time_of_execution,
                    'n': time_of_execution
                }
                self._schedule_on_celery(task_func_name, task_kwargs, i, 0)
                if self._test_mode is False:
                    time.sleep(sleep_time)
                else:
                    self.test_waiting_time_history.append(sleep_time)

            self.logger.info('Generation round {} completed. '
                             '{} tasks have been scheduled in this round for a total of {}'.format(
                0, tasks_to_generate, self.tasks_scheduled), resource='TaskGenerator')
            self.logger.info('All the {} eval tasks for the run have been scheduled'.format(self.tasks_scheduled))
            self.system_producer.publish_scheduling_completed_event(
                phase=RunPhase.RUN,
                task_scheduled=self.tasks_scheduled)
        else:
            raise AttributeError('RunConfig is None, cannot schedule tasks')

    def get_global_stats(self, prepare_time, start_execution_time):
        if self.run_config is not None:
            return {
                'task_generator_seed': self.run_config.task_generator_random_seed(),
                'tasks_to_generate': self.run_config.tasks_to_generate_total_number(),
                'tasks_distribution_config': self.run_config.tasks_to_generate(),
                'tasks_to_bootstrap': self.run_config.tasks_bootstrapping_tasks_to_generate(),
                'tasks_bootstrapping_config': self.run_config.task_bootstrapping(),
                'features_enabled': self.run_config.features_enabled(),
                'state_features': list(self.run_config.state_features().keys()),
                'context_features': list(self.run_config.context_features().keys()),
                'prepare_time': prepare_time,
                'start_execution_time': start_execution_time,
                'functions': self.run_config.functions()
            }
        else:
            raise AttributeError('RunConfig is None, cannot get global stats')

    def start(self):
        try:
            self.is_ready = True
            self.logger.info('TaskGenerator is ready and it is waiting for StartRun events', resource='TaskGenerator')
        except Exception as e:
            self.logger.exception(e)
            self.is_ready = False

    def stop(self):
        self.is_ready = False
        self.logger.info('TaskGenerator have been stopped', resource='TaskGenerator')
