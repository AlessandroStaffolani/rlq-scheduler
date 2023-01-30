from rlq_scheduler.common.system_events.event import SchedulingStartedEvent, \
    SchedulingCompletedEvent, PrepareNewRunEvent, RunCompletedEvent, ResourceStatusChangedEvent, StartRunEvent, \
    ExecutionCompletedEvent, RunPhase
from rlq_scheduler.common.system_status import ResourceStatus
from rlq_scheduler.common.utils.decorators import consumer_callback_fetch_exceptions
from rlq_scheduler.trajectory_collector.trajectory_collector_context import TrajectoryCollectorContext


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_resource_status_changed_event(event: ResourceStatusChangedEvent, context: TrajectoryCollectorContext):
    if event.resource_name == 'system_manager' and event.resource_status == ResourceStatus.RUNNING:
        context.init_resource()
    if event.resource_name == context.name and event.resource_status != context.status:
        context.status = event.resource_status


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_prepare_new_run_event(event: PrepareNewRunEvent, context: TrajectoryCollectorContext):
    if context.status == ResourceStatus.WAITING:
        context.prepare_run(run_config=event.new_run_config, prepare_time=event.timestamp)
    else:
        context.logger.warning('{} is in {} but it receives PrepareNewRunEvent'
                               .format(context.visual_name, context.status),
                               resource='TrajectoryCollectorSystemConsumerCallback')


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_start_run_event(event: StartRunEvent, context: TrajectoryCollectorContext):
    if context.status == ResourceStatus.READY:
        context.logger.info('Staring run with code: {}'.format(event.run_code),
                            resource='TrajectoryCollectorSystemConsumerCallback')
        context.start_run(start_time=event.timestamp)
    else:
        context.logger.warning('{} is in {} but it receives StartRunEvent'.format(context.visual_name, context.status),
                               resource='TrajectoryCollectorSystemConsumerCallback')


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_scheduling_started_event(event: SchedulingStartedEvent, context: TrajectoryCollectorContext):
    context.current_phase = event.phase
    context.trajectory_builder.current_phase = event.phase
    if context.current_phase == RunPhase.RUN:
        context.trajectory_builder.task_to_execute = event.task_to_generate
        context.trajectory_builder.task_completed = context.current_run_config.tasks_to_skip_total()


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_scheduling_completed_event(event: SchedulingCompletedEvent, context: TrajectoryCollectorContext):
    if context.current_phase == RunPhase.RUN:
        task_scheduled = event.task_scheduled
        if task_scheduled != context.trajectory_builder.task_to_execute:
            context.trajectory_builder.task_to_execute = task_scheduled


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_execution_completed_event(event: ExecutionCompletedEvent, context: TrajectoryCollectorContext):
    if context.current_phase == RunPhase.RUN:
        context.current_run_end_execution_time = event.timestamp
        context.save_tasks_succeeded_and_failed_stat(context.trajectory_builder.task_completed,
                                                     context.trajectory_builder.task_failed)
        if not context.trajectory_saver.disabled:
            context.trajectory_saver.flush()
        context.current_phase = RunPhase.WAIT
    elif context.current_phase == RunPhase.BOOTSTRAP:
        context.trajectory_builder.task_completed = context.current_run_config.tasks_to_skip_total()
        context.trajectory_builder.reward_function.reset_internal_state()


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_run_completed_event(event: RunCompletedEvent, context: TrajectoryCollectorContext):
    if context.status == ResourceStatus.RUNNING:
        context.logger.info('Stopping run resources because run with code: {} is completed'.format(event.run_code),
                            resource='TrajectoryCollectorSystemConsumerCallback')
        context.stop_run_resources(end_run_time=event.timestamp)


SYSTEM_CONSUMER_CALLBACKS = {
    'generic_event_callback': None,
    'system_status_changed_event_callback': None,
    'resource_status_changed_event_callback': handle_resource_status_changed_event,
    'prepare_new_run_event_callback': handle_prepare_new_run_event,
    'start_run_event_callback': handle_start_run_event,
    'stats_updated_event_callback': None,
    'scheduling_started_event_callback': handle_scheduling_started_event,
    'trajectory_completed_event_callback': None,
    'scheduling_completed_event_callback': handle_scheduling_completed_event,
    'execution_completed_event_callback': handle_execution_completed_event,
    'run_completed_event_callback': handle_run_completed_event
}
