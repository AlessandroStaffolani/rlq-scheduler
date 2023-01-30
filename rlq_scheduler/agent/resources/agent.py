import json
import time
from enum import Enum, auto
from logging import Logger

from flask import Response, request
from flask_restful import Resource

from rlq_scheduler.agent.agent_context import AgentContext
from rlq_scheduler.common.exceptions import NoStateFoundForTrajectoryException
from rlq_scheduler.common.stats import AssignmentEntry
from rlq_scheduler.common.trajectory import Trajectory, TrajectoryProperties
from rlq_scheduler.common.utils.encoders import NumpyEncoder
from rlq_scheduler.common.validation_reward import ValidationStructItem, empty_validation_struct


class AsyncTask(Enum):
    TRAJECTORY_ACTION_UPDATE = auto()
    TRAJECTORY_CONTEXT_UPDATE = auto()
    TRAJECTORY_ACTION_AND_CONTEXT_UPDATE = auto()
    UPDATE_STATS = auto()


class AsyncTaskItem:

    def __init__(self, task_type, parameters):
        if task_type not in AsyncTask:
            raise TypeError('type must be of AsyncTask enum type')
        if not isinstance(parameters, dict):
            raise TypeError('Task parameters must be a dictionary with the parameters of the task to execute')
        self._task_type = task_type
        self._task_parameters = parameters

    def task_type(self):
        return self._task_type

    def task_parameters(self):
        return self._task_parameters


class AgentActionResource(Resource):
    def __init__(self, context: AgentContext):
        self.agent_context = context
        self.logger: Logger = context.logger

    def get(self, task_id):
        try:
            args = request.args.to_dict()
            if 'task_class' in args:
                task_class = args['task_class']
            else:
                raise AttributeError('No task_class provided in query parameters')
            if 'task_params' in args:
                task_params = args['task_params']
                self.logger.debug(f'Agent received task_params = {task_params} | agent args = {args}')
            else:
                raise AttributeError('No task_params provided in query parameters')
            self.logger.debug('Agent received for task_id {} args = {}'.format(task_id, task_class),
                              resource='AgentApiResource')
            state = None
            full_start = time.time()
            if self.agent_context.agent.need_state:
                state = self.agent_context.trajectory_backend.get_if_not_none_or_wait_update(
                    task_id,
                    prop=TrajectoryProperties.STATE,
                    max_retry=3)
                state = Trajectory.deserialize_trajectory_vector(state)
                if state is None:
                    self.logger.warning('Trajectory state for task {} is None'.format(task_id),
                                        resource='AgentApiResource')
                    raise NoStateFoundForTrajectoryException(task_id)
                else:
                    self.logger.debug('State for trajectory with id {} is {}'.format(task_id, state),
                                      resource='AgentApiResource')
            agent_start = time.time()
            action, action_index, context, epsilon = self.agent_context.agent.choose_action(
                state=state,
                task_class=task_class,
                state_builder=self.agent_context.state_builder
            )
            full_end = time.time()
            agent_end = full_end
            self.logger.debug('Agent at time {} choose action: {} | action_index: {} | context: {} | epsilon: {}'
                              .format(self.agent_context.agent.t, action, action_index, context, epsilon),
                              resource='AgentApiResource')

            # async update of the trajectory
            self.agent_context.agent_async_thread_pool.apply_async(
                self._update_trajectory_action_and_context,
                kwds={
                    'trajectory_id': task_id,
                    'action': action_index,
                    'context': context
                },
                error_callback=lambda e: self.logger.exception(e)
            )

            # async update time window state features
            self.agent_context.agent_async_thread_pool.apply_async(
                self._update_state_window_features,
                kwds={
                    'task_class': task_class,
                    'worker_class': action
                },
                error_callback=lambda e: self.logger.exception(e)
            )

            # async creation of the validation reward entry for the current trajectory
            self.agent_context.agent_async_thread_pool.apply_async(
                self._create_trajectory_validation_record,
                kwds={
                    'trajectory_id': task_id,
                    'time_step': self.agent_context.agent.t
                },
                error_callback=lambda e: self.logger.exception(e)
            )

            # async update of the stats
            self.agent_context.agent_async_thread_pool.apply_async(
                self._update_stats,
                kwds={
                    'epsilon_value': epsilon,
                    'epsilon_step': self.agent_context.agent.t,
                    'full_time': full_end - full_start,
                    'agent_time': agent_end - agent_start,
                    'task_id': task_id,
                    'action': action_index,
                    'worker_class': action,
                    'task_name': task_class,
                    'time_step': self.agent_context.agent.t,
                    'task_params': task_params
                },
                error_callback=lambda e: self.logger.exception(e)
            )

            # async save agent's model checkpoint
            self.agent_context.agent_async_thread_pool.apply_async(
                self.agent_context.save_agent_checkpoint,
                kwds={
                    'step': self.agent_context.agent.t,
                    'frequency': self.agent_context.current_run_config.checkpoint_frequency(),
                    'step_name': 'time-step',
                    'use_loss': False
                },
                error_callback=lambda e: self.logger.exception(e)
            )

            res = Response(
                response=json.dumps(
                    {
                        'action': {
                            'label': action,
                            'index': action_index
                        },
                        'current_run_code': self.agent_context.current_run_code
                    }, cls=NumpyEncoder),
                status=200,
                headers=[("Content-Type", "application/json")]
            )
            return res
        except NoStateFoundForTrajectoryException as e:
            self.logger.error(e)
            res = Response(
                response=json.dumps({'message': str(e)}),
                status=400,
                headers=[("Content-Type", "application/json")]
            )
            return res
        except AttributeError as e:
            self.logger.error(e)
            res = Response(
                response=json.dumps({'message': str(e)}),
                status=400,
                headers=[("Content-Type", "application/json")]
            )
            return res
        except Exception as e:
            self.logger.exception(e)
            res = Response(
                response=json.dumps({'message': 'An error occurred while choosing an action'}),
                status=500,
                headers=[("Content-Type", "application/json")]
            )
            return res

    def store_epsilon(self, value, step):
        self.save_stats_property_value('epsilon', value, as_list=True)
        self.add_scalar('epsilon', value, step)

    def save_stats_property_value(self, prop, value, as_list=False):
        if value is not None:
            result = self.agent_context.stats_backend.save_stats_group_property(
                stats_run_code=self.agent_context.current_run_code,
                prop=prop,
                value=value,
                as_list=as_list
            )
            self.logger.debug('Added {} to stats, with value: {}'.format(prop, value), resource='AgentApiResource')

    def add_scalar(self, tag, value, step):
        if self.agent_context.global_config.is_tensorboard_enabled():
            if self.agent_context.tensorboard is not None and value is not None:
                self.agent_context.tensorboard.add_scalar(tag, value, step)
            elif value is not None:
                self.logger.warning('Value is not None, but tensorboard is still None. tag: {} | value: {} | step: {}'
                                    .format(tag, value, step), resource='AgentApiResource')

    # def _async_worker_callback(self):
    #     try:
    #         self.logger.info('Starting AgentAsyncWorker', resource='AgentApiResource')
    #         while not self.agent_context.agent_stop_async_thread_event.is_set():
    #             item: AsyncTaskItem = self.agent_context.agent_async_task_queue.get()
    #             switcher = {
    #                 AsyncTask.TRAJECTORY_ACTION_UPDATE: self._update_trajectory_action,
    #                 AsyncTask.TRAJECTORY_CONTEXT_UPDATE: self._update_trajectory_context,
    #                 AsyncTask.TRAJECTORY_ACTION_AND_CONTEXT_UPDATE: self._update_trajectory_action_and_context,
    #                 AsyncTask.UPDATE_STATS: self._update_stats
    #             }
    #             self.logger.debug('AgentAsyncWorker is executing action: {}'.format(item.task_type())
    #                               , resource="AgentApiResource")
    #             task_function = switcher[item.task_type()]
    #             task_function(**item.task_parameters())
    #         self.logger.info('AgentAsyncWorker has been stopped', resource='AgentApiResource')
    #     except Exception as e:
    #         self.logger.exception(e)

    def _update_trajectory_action(self, trajectory_id, action):
        self.agent_context.trajectory_backend.update_property(
            trajectory_id=trajectory_id,
            value=action,
            prop=TrajectoryProperties.ACTION)
        self.logger.debug('Set action {} into the trajectory with id {}'.format(action, trajectory_id),
                          resource='AgentApiResource')

    def _update_state_window_features(self, task_class, worker_class):
        features = self.agent_context.current_run_config.state_features()
        if 'resource_usage' in features:
            self.agent_context.state_builder.add_resource_usage_entry(worker_class)
        if 'task_frequency' in features:
            self.agent_context.state_builder.add_task_frequency_entry(task_class)
        self.logger.debug('Add resource usage entry and task frequency entry, if enabled')

    def _update_trajectory_context(self, trajectory_id, context):
        self.agent_context.trajectory_backend.update_property(
            trajectory_id=trajectory_id,
            value=context,
            prop=TrajectoryProperties.CONTEXT)
        self.logger.debug('Set context {} into the trajectory with id {}'.format(context, trajectory_id),
                          resource='AgentApiResource')

    def _update_trajectory_action_and_context(self, trajectory_id, action, context):
        self.agent_context.trajectory_backend.update_property(
            trajectory_id=trajectory_id,
            value=action,
            prop=TrajectoryProperties.ACTION)
        self.agent_context.trajectory_backend.update_property(
            trajectory_id=trajectory_id,
            value=context,
            prop=TrajectoryProperties.CONTEXT)
        self.logger.debug('Set action {} and context {} into the trajectory with id {}'
                          .format(action, context, trajectory_id), resource='AgentApiResource')

    def _create_trajectory_validation_record(self, trajectory_id: str, time_step: int):
        validation_struct: dict = empty_validation_struct()
        validation_struct[ValidationStructItem.TIME_STEP] = time_step
        json_struct = json.dumps(validation_struct)
        key = f'{self.agent_context.global_config.backend_validation_reward_prefix()}_{trajectory_id}'
        self.agent_context.backend.save(key, value=json_struct)

    def _update_stats(self, epsilon_value, epsilon_step, full_time, agent_time,
                      task_id, action, worker_class, task_name, time_step, task_params):
        self.store_epsilon(epsilon_value, epsilon_step)
        self.save_stats_property_value('full_agent_get_action_time', full_time, as_list=True)
        self.save_stats_property_value('agent_get_action_time', agent_time, as_list=True)
        self._create_assignment_entry(
            task_id, action, worker_class, task_name, time_step, task_params
        )
        self.logger.debug('Updated agent stats')

    def _create_assignment_entry(self, task_id, action, worker_class, task_name, time_step, task_params):
        assignment_entry = AssignmentEntry(
            task_id=task_id,
            action=action,
            worker_class=worker_class,
            reward=None,
            task_name=task_name,
            time_step=time_step,
            agent=self.agent_context.agent.name,
            task_params=task_params
        )
        key = f'{self.agent_context.global_config.backend_assignment_entry_prefix()}_{task_id}'
        result = self.agent_context.backend.save(key=key, value=assignment_entry.to_json())
        if result is True:
            self.logger.info(f'Added assignment entry for task {assignment_entry.task_id}')
        else:
            self.logger.error(f'Impossible to add assignment entry for task {assignment_entry.task_id}')
