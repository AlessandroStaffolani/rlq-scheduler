import json
import os
import time
from multiprocessing.pool import ThreadPool

import numpy as np

from rlq_scheduler.agent.agents.agent_utils import create_agent_from_config, get_agent_model_to_load
from rlq_scheduler.agent.agents.base import BaseAgent
from rlq_scheduler.common.backends.base_backend import BaseTrajectoryBackend, BaseBackend
from rlq_scheduler.common.config_helper import AgentConfigHelper
from rlq_scheduler.common.resource_context import Context
from rlq_scheduler.common.run_config import RunConfig, generate_run_name
from rlq_scheduler.common.state.state import Features
from rlq_scheduler.common.state.state_builder import StateBuilder
from rlq_scheduler.common.stats import AssignmentEntry
from rlq_scheduler.common.system_events.event import RunPhase
from rlq_scheduler.common.system_status import ResourceStatus
from rlq_scheduler.common.tensorboard_wrapper import TensorboardWrapper
from rlq_scheduler.common.trajectory import Trajectory
from rlq_scheduler.common.utils.decorators import class_fetch_exceptions
from rlq_scheduler.common.validation_reward import parse_validation_json_struct, ValidationStructItem


class AgentContext(Context):

    def __init__(self,
                 config_filename,
                 global_config_filename,
                 system_consumer_callbacks
                 ):
        self.config: AgentConfigHelper = AgentConfigHelper(config_path=config_filename)
        super(AgentContext, self).__init__(global_config_filename=global_config_filename,
                                           system_consumer_callbacks=system_consumer_callbacks,
                                           config=self.config,
                                           name='Agent')
        self.backend: BaseBackend = None
        self.trajectory_backend: BaseTrajectoryBackend = None
        self.state_builder: StateBuilder = None
        self.agent: BaseAgent = None
        self.agent_async_thread_pool = ThreadPool(processes=5)
        self.tensorboard: TensorboardWrapper = None
        self.run_name = None
        self.previous_observed_trajectory_id = None

    @class_fetch_exceptions(publish_error=True, is_context=True)
    def init_resource(self):
        if self.resources_initialized is False:
            self._init_primary_components()
            self.backend: BaseBackend = self._init_backend(backed_type='base')
            self.trajectory_backend: BaseTrajectoryBackend = self._init_backend(backed_type='trajectory')
            self.state_builder: StateBuilder = StateBuilder(
                global_config=self.global_config,
                logger=self.logger,
                is_workers_load_local=False
            )
            self._init_final_action()
            self.resources_initialized = True
        else:
            self.logger.warning('Init resources called more than once for {}'.format(self.name),
                                resource='AgentContext')

    @class_fetch_exceptions(publish_error=True, is_context=True)
    def prepare_run(self, run_config: RunConfig, prepare_time: float or None):
        try:
            super().prepare_run(run_config, prepare_time)
            agent_model = self._get_agent_model(run_config)
            self.agent: BaseAgent = create_agent_from_config(
                agent_config=run_config.config.agent_config(agent_type=run_config.config.agent_type()),
                global_config=self.global_config,
                run_config=run_config.config,
                agent_model=agent_model,
                logger=self.logger
            )
            self.agent.run_code = run_config.run_code
            self.logger.info('Agent {} initialized with parameters: {}'.format(self.agent, self.agent.get_parameters()),
                             resource='AgentContext')
            features = Features(
                global_config=self.global_config,
                run_config=run_config.config,
                worker_classes=run_config.config.available_worker_classes(),
                task_classes=run_config.config.available_tasks_classes())
            self.state_builder.set_run_config(run_config.config)
            self.state_builder.set_state_features(features)
            self._prepare_tensorboard()
            if not self.trajectory_saver.disabled:
                self.trajectory_saver.save_run_info(
                    run_code=self.current_run_code,
                    agent_name=self.agent.full_name(),
                    agent_parameters=self.agent.get_parameters()
                )
            self.change_resource_status(ResourceStatus.READY)
        except Exception as e:
            self.logger.exception(e)
            self.change_resource_status(ResourceStatus.ERROR)

    def _get_agent_model(self, run_config: RunConfig):
        model_path = get_agent_model_to_load(run_config.config.agent_config(agent_type=run_config.config.agent_type()))
        model = None
        if model_path is not None:
            model = self.object_handler.load(file_path=model_path, pickle_encoding=True)
        return model

    def _prepare_tensorboard(self):
        if self.current_run_config is not None:
            task_to_generate = self.current_run_config.tasks_to_generate_total_number()
            self.run_name = generate_run_name(self.current_run_code,
                                              task_executed=task_to_generate,
                                              start_time=self.current_run_prepare_time)
            if self.global_config.is_tensorboard_enabled():
                log_dir = os.path.join(
                    self.global_config.tensorboard_log_dir_base(),
                    self.current_run_config.run_name_prefix(),
                    'tensorboard',
                    'train' if self.agent.train else 'eval',
                    self.agent.full_name(),
                    self.run_name)
                transport = self.global_config.tensorboard_transport()
                self.logger.info('Starting tensorboard with logdir: {} and transport: {}'.format(log_dir, transport),
                                 resource='AgentContext')
                self.tensorboard = TensorboardWrapper(log_dir=log_dir,
                                                      transport=transport,
                                                      logger=self.logger)

    def start_run(self, start_time: float):
        super().start_run(start_time)
        self.current_run_stats.set_agent_stats(
            agent_type=self.agent.full_name(),
            agent_parameters=self.agent.get_parameters(),
            agent_model=get_agent_model_to_load(
                self.current_run_config.agent_config(agent_type=self.current_run_config.agent_type()))
        )
        result = self.stats_backend.save_stats_group(
            stats_run_code=self.current_run_code,
            group=self.current_run_stats.agent_stats)
        if result is True:
            self.logger.info('Agent stats have been saved', resource='AgentContext')
            self.system_producer.publish_stats_updated_event(run_code=self.current_run_code,
                                                             stat_group='agent_stats')
        else:
            self.logger.warning('Error while saving agent stats', resource='AgentContext')
        self.change_resource_status(ResourceStatus.RUNNING)

    def stop_run_resources(self, end_run_time: float or None):
        super().stop_run_resources(end_run_time)
        if self.tensorboard is not None:
            self.tensorboard.close()
        self.agent.stats_backend.backend.close()
        self.change_resource_status(ResourceStatus.WAITING)

    def observe_reward(self, trajectory_id: str):
        # check if I'm observing twice the last trajectory id
        if self.previous_observed_trajectory_id != trajectory_id:
            trajectory: Trajectory = self.trajectory_backend.get(trajectory_id)
            # check if the trajectory with trajectory_id exists
            if trajectory is not None:
                reward = trajectory.reward()
                if self.current_phase == RunPhase.RUN:
                    self.add_tensorboard_scalar('cumulative_reward', self.agent.total_reward,
                                                step=self.agent.n_reward_observation)
                reward_multiplied = self.agent.multiply_reward(reward)
                self.logger.debug(
                    'Reward for trajectory {} is {}, using reward multiplier {} limited to {} it becomes {}'
                        .format(trajectory.id(), trajectory.reward(),
                                self.agent.reward_multiplier,
                                self.agent.reward_multiplier_limit,
                                reward_multiplied),
                    resource='AgentContext')
                action = trajectory.action()
                state = trajectory.state()
                next_state = trajectory.next_state()
                context = trajectory.context()
                loss = self.agent.observe_delayed_action(
                    action=action,
                    reward=reward_multiplied,
                    state=state,
                    next_state=next_state,
                    context=context
                )
                if self.current_phase == RunPhase.RUN:
                    self.add_tensorboard_scalar('loss', loss, step=self.agent.n_reward_observation)
                self.agent.push_experience_entry(
                    state=state,
                    action=action,
                    reward=reward_multiplied,
                    next_state=next_state
                )
                self.update_validation_reward_entry(
                    trajectory_id=trajectory.id(),
                    reward=reward_multiplied
                )
                self.update_assignment_entry_reward(trajectory.id(), reward=reward_multiplied, phase=self.current_phase)
                self.logger.info('Agent has observed the reward from trajectory {}'.format(trajectory.id()),
                                 resource='AgentContext')
                if self.trajectory_saver is not None:
                    self.trajectory_saver.push_trajectory(trajectory_id=trajectory_id)
                # if self.current_phase == RunPhase.RUN:
                # self.save_agent_checkpoint(
                #     step=self.agent.n_reward_observation,
                #     frequency=self.current_run_config.checkpoint_frequency(),
                #     step_name='reward-observation',
                #     use_loss=True
                # )
                if self.current_phase == RunPhase.BOOTSTRAP:
                    tasks_to_bootstrap = self.current_run_config.tasks_bootstrapping_tasks_to_generate()
                    self.logger.debug('Tasks observed = {} while tasks to bootstrap = {}'
                                      .format(self.agent.n_reward_observation, tasks_to_bootstrap))
                    if self.agent.n_reward_observation + 1 == tasks_to_bootstrap:
                        self.system_producer.publish_execution_completed_event(
                            phase=RunPhase.BOOTSTRAP,
                            task_executed=tasks_to_bootstrap
                        )
            else:
                self.logger.error('No trajectory has been found for id {}'.format(trajectory_id),
                                  resource='AgentContext')
        else:
            self.logger.warning(f'Received trajectory with same id of the previous.'
                                f' previous id: {self.previous_observed_trajectory_id}  current: {trajectory_id}',
                                resource='AgentContext')

    def add_tensorboard_scalar(self, tag, value, step):
        if self.tensorboard is not None and value is not None:
            self.tensorboard.add_scalar(tag, value, step)

    def update_assignment_entry_reward(self, task_id, reward, phase):
        key = f'{self.global_config.backend_assignment_entry_prefix()}_{task_id}'
        entry_str = self.backend.get(key)
        if entry_str is not None:
            entry_dict = json.loads(entry_str)
            entry_dict['reward'] = reward
            entry_dict['updated_at'] = time.time()
            entry_dict['phase'] = phase if phase is not None else RunPhase.RUN
            entry = AssignmentEntry(**entry_dict)
            self.backend.save(key=key, value=entry.to_json())
        else:
            self.logger.warning('Impossible to update assignment_entry for task {} entry not present in backend'
                                .format(task_id))

    def save_all_assignment_entries(self):
        key_pattern = f'{self.global_config.backend_assignment_entry_prefix()}_*'
        all_entries_str = self.backend.get_all(key_pattern=key_pattern)
        # all_entries_parsed = [json.loads(entry) for entry in all_entries_str]
        self.stats_backend.save_stats_group_property(
            stats_run_code=self.current_run_code,
            prop='assignments_history',
            value=all_entries_str,
            as_list=True
        )

    def get_checkpoint_folder(self):
        return os.path.join(
            self.current_run_config.run_name_prefix(),
            self.agent.save_model_config['folder'],
            'checkpoints',
            self.agent.full_name(),
            self.run_name
        )

    def get_model_folder(self):
        return os.path.join(
            self.current_run_config.run_name_prefix(),
            self.agent.save_model_config['folder'],
            'train' if self.agent.train else 'eval',
            self.agent.full_name()
        )

    def save_agent_checkpoint(self, step: int, frequency: int, step_name: str, use_loss=True):
        if self.agent.train is True:
            if step % frequency == 0:
                if self.run_name is not None:
                    path = self.get_checkpoint_folder()
                    filename = f'{step_name}={step}'
                    loss_mean = None
                    if use_loss:
                        loss_mean = self.agent_loss_interval_mean()
                    if loss_mean is not None:
                        filename += f'_loss-avg={loss_mean}'
                    serialized_agent = self.agent.get_serializable_content()
                    self.object_handler.save(
                        obj=serialized_agent,
                        filename=f'{filename}.pth',
                        path=path,
                        pickle_encoding=True,
                        max_retries=5,
                        trial=0,
                        wait_timeout=60
                    )
                    self.logger.info('Saved agent checkpoint at {} number: {}'
                                     .format(step_name, step), resource='AgentContext')
                else:
                    self.logger.warning('Save checkpoint has been called but run_name is None',
                                        resource='AgentContext')

    def agent_loss_interval_mean(self):
        if len(self.agent.losses) > 0:
            check_point = self.current_run_config.checkpoint_frequency()
            n = self.agent.n_reward_observation
            losses_array = np.array(self.agent.losses[n - check_point: -1])
            return losses_array.mean()
        else:
            return None

    def update_validation_reward_entry(self, trajectory_id: int, reward: float):
        if self.agent.train is True:
            key = f'{self.global_config.backend_validation_reward_prefix()}_{trajectory_id}'
            validation_struct = parse_validation_json_struct(self.backend.get(key))
            validation_struct[ValidationStructItem.REWARD] = reward
            validation_struct[ValidationStructItem.UPDATED_AT] = time.time()
            json_struct = json.dumps(validation_struct)
            self.backend.save(key, value=json_struct)

    def save_agent_model(self):
        if self.agent.is_save_model_enabled():
            if self.run_name is not None:
                path = self.get_model_folder()
                serialized_agent = self.agent.get_serializable_content()
                self.object_handler.save(
                    obj=serialized_agent,
                    filename=f'{self.run_name}.pth',
                    path=path,
                    pickle_encoding=True,
                    max_retries=5,
                    trial=0,
                    wait_timeout=60
                )
            else:
                self.logger.warning('Save agent model has been called but no run_name has been defined',
                                    resource='AgentContext')

    def stop(self):
        self.state_builder.backend.close()
        super().stop()

    def resources(self):
        resources = super().resources()
        resources.update({
            'config': self.config,
            'backend': self.trajectory_backend,
            'agent': self.agent
        })
        return resources
