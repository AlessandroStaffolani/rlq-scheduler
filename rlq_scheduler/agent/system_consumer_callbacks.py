from rlq_scheduler.agent.agent_context import AgentContext
from rlq_scheduler.common.saving_modes import save_model_run
from rlq_scheduler.common.system_events.event import ResourceStatusChangedEvent, ExecutionCompletedEvent, \
    PrepareNewRunEvent, RunCompletedEvent, StartRunEvent, TrajectoryCompletedEvent, RunPhase, SchedulingStartedEvent
from rlq_scheduler.common.system_status import ResourceStatus
from rlq_scheduler.common.utils.decorators import consumer_callback_fetch_exceptions
from rlq_scheduler.common.validation_reward import get_average_validation_reward_for_interval, save_best_checkpoint


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_resource_status_changed_evend(event: ResourceStatusChangedEvent, context: AgentContext):
    if event.resource_name == 'system_manager' and event.resource_status == ResourceStatus.RUNNING:
        context.init_resource()
    if event.resource_name == context.name and event.resource_status != context.status:
        context.status = event.resource_status


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_prepare_new_run_event(event: PrepareNewRunEvent, context: AgentContext):
    if context.status == ResourceStatus.WAITING:
        context.prepare_run(run_config=event.new_run_config, prepare_time=event.timestamp)
    else:
        context.logger.warning('{} is in {} but it receives PrepareNewRunEvent'
                               .format(context.visual_name, context.status), resource='AgentSystemConsumerCallback')


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_start_run_event(event: StartRunEvent, context: AgentContext):
    if context.status == ResourceStatus.READY:
        context.logger.info('Staring run with code: {}'.format(event.run_code), resource='AgentSystemConsumerCallback')
        context.start_run(start_time=event.timestamp)
    else:
        context.logger.warning('{} is in {} but it receives StartRunEvent'.format(context.visual_name, context.status),
                               resource='AgentSystemConsumerCallback')


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_scheduling_started_event(event: SchedulingStartedEvent, context: AgentContext):
    context.current_phase = event.phase


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_trajectory_completed_event(event: TrajectoryCompletedEvent, context: AgentContext):
    if context.status == ResourceStatus.RUNNING:
        context.observe_reward(event.trajectory_id)
    else:
        context.logger.warning('{} is in {} but it receives TrajectoryCompletedEvent'
                               .format(context.visual_name, context.status), resource='AgentSystemConsumerCallback')


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_execution_completed_event(event: ExecutionCompletedEvent, context: AgentContext):
    if event.phase == RunPhase.RUN:
        context.current_run_end_execution_time = event.timestamp
        result = context.stats_backend.save_stats_group_property(
            stats_run_code=context.agent.run_code,
            prop='selected_actions',
            value=context.agent.action_attempts
        )
        result_2 = context.stats_backend.save_stats_group_property(
            stats_run_code=context.agent.run_code,
            prop='single_run_selected_actions',
            value=context.agent.single_run_action_attempts
        )
        context.save_all_assignment_entries()
        # save validation reward
        max_checkpoint_index, max_validation_reward_avg = get_average_validation_reward_for_interval(
            global_config=context.global_config,
            run_config=context.current_run_config,
            backend=context.backend,
            stats_backend=context.stats_backend,
            current_run=context.current_run_code,
            logger=context.logger
        )
        context.logger.info('Max checkpoint validation reward average is {}. Correspondent checkpoint index is {}'
                            .format(max_validation_reward_avg, max_checkpoint_index))
        # save best model
        if context.agent.train is True:
            save_model_run(
                config=context.current_run_config,
                saving_folder=context.get_model_folder(),
                run_name=context.run_name,
                agent=context.agent,
                handler=context.object_handler,
                logger=context.logger,
                best_checkpoint_index=max_checkpoint_index,
                checkpoint_folder=context.get_checkpoint_folder()
            )
        if result is True and result_2 is True:
            context.logger.info('selected_actions and single_run_selected_actions stats have been saved',
                                resource='AgentSystemConsumerCallback')
            context.system_producer.publish_stats_updated_event(run_code=context.current_run_code,
                                                                stat_group='execution_history_stats')
        else:
            context.logger.warning('Error while saving selected_actions and single_run_selected_actions stat',
                                   resource='AgentSystemConsumerCallback')
        if not context.trajectory_saver.disabled:
            context.trajectory_saver.flush()
        context.current_phase = RunPhase.WAIT


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_run_completed_event(event: RunCompletedEvent, context: AgentContext):
    if context.status == ResourceStatus.RUNNING:
        context.logger.info('Stopping run resources because run with code: {} is completed'.format(event.run_code),
                            resource='AgentSystemConsumerCallback')
        context.stop_run_resources(end_run_time=event.timestamp)
    else:
        context.logger.warning('{} is in {} but it receives RunCompletedEvent'
                               .format(context.visual_name, context.status), resource='AgentSystemConsumerCallback')


SYSTEM_CONSUMER_CALLBACKS = {
    'generic_event_callback': None,
    'system_status_changed_event_callback': None,
    'resource_status_changed_event_callback': handle_resource_status_changed_evend,
    'prepare_new_run_event_callback': handle_prepare_new_run_event,
    'start_run_event_callback': handle_start_run_event,
    'stats_updated_event_callback': None,
    'scheduling_started_event_callback': handle_scheduling_started_event,
    'trajectory_completed_event_callback': handle_trajectory_completed_event,
    'scheduling_completed_event_callback': None,
    'execution_completed_event_callback': handle_execution_completed_event,
    'run_completed_event_callback': handle_run_completed_event
}


