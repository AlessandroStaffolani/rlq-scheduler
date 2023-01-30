from rlq_scheduler.common.system_events.event import StartRunEvent, PrepareNewRunEvent, RunCompletedEvent, \
    ResourceStatusChangedEvent, ExecutionCompletedEvent, SchedulingCompletedEvent, RunPhase, SchedulingStartedEvent
from rlq_scheduler.common.system_status import ResourceStatus
from rlq_scheduler.common.utils.decorators import consumer_callback_fetch_exceptions
from rlq_scheduler.task_generator.task_generator_context import TaskGeneratorContext


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_resource_status_changed_evend(event: ResourceStatusChangedEvent, context: TaskGeneratorContext):
    if event.resource_name == 'system_manager' and event.resource_status == ResourceStatus.RUNNING:
        context.init_resource()
    if event.resource_name == context.name and event.resource_status != context.status:
        context.status = event.resource_status


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_prepare_new_run_event(event: PrepareNewRunEvent, context: TaskGeneratorContext):
    if context.status == ResourceStatus.WAITING:
        context.prepare_run(run_config=event.new_run_config, prepare_time=event.timestamp)
    else:
        context.logger.warning('{} is in {} but it receives PrepareNewRunEvent'
                               .format(context.visual_name, context.status),
                               resource='TasKGeneratorSystemConsumerCallback')


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_start_run_event(event: StartRunEvent, context: TaskGeneratorContext):
    if context.status == ResourceStatus.READY:
        context.logger.info('Staring run with code: {}'.format(event.run_code),
                            resource='TasKGeneratorSystemConsumerCallback')
        context.start_run(start_time=event.timestamp)
    else:
        context.logger.warning('{} is in {} but it receives StartRunEvent'.format(context.visual_name, context.status),
                               resource='TasKGeneratorSystemConsumerCallback')


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_scheduling_started_event(event: SchedulingStartedEvent, context: TaskGeneratorContext):
    context.current_phase = event.phase


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_scheduling_completed_event(event: SchedulingCompletedEvent, context: TaskGeneratorContext):
    if event.phase == RunPhase.RUN:
        context.save_stats_property_value('tasks_generated', value=context.task_generator.scheduled_task_stats)
        context.system_producer.publish_stats_updated_event(run_code=context.current_run_code,
                                                            stat_group='tasks_generated')


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_execution_completed_event(event: ExecutionCompletedEvent, context: TaskGeneratorContext):
    if event.phase == RunPhase.RUN:
        context.current_run_end_execution_time = event.timestamp
        if not context.trajectory_saver.disabled:
            context.trajectory_saver.flush()
        context.current_phase = RunPhase.WAIT
    elif event.phase == RunPhase.BOOTSTRAP:
        context.task_generator.schedule_tasks()


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_run_completed_event(event: RunCompletedEvent, context: TaskGeneratorContext):
    if context.status == ResourceStatus.RUNNING:
        context.logger.info('Stopping run resources because run with code: {} is completed'.format(event.run_code),
                            resource='TasKGeneratorSystemConsumerCallback')
        context.stop_run_resources(end_run_time=event.timestamp)
    else:
        context.logger.warning('{} is in {} but it receives RunCompletedEvent'
                               .format(context.visual_name, context.status),
                               resource='TasKGeneratorSystemConsumerCallback')


SYSTEM_CONSUMER_CALLBACKS = {
    'generic_event_callback': None,
    'system_status_changed_event_callback': None,
    'resource_status_changed_event_callback': handle_resource_status_changed_evend,
    'prepare_new_run_event_callback': handle_prepare_new_run_event,
    'start_run_event_callback': handle_start_run_event,
    'stats_updated_event_callback': None,
    'scheduling_started_event_callback': handle_scheduling_started_event,
    'trajectory_completed_event_callback': None,
    'scheduling_completed_event_callback': handle_scheduling_completed_event,
    'execution_completed_event_callback': handle_execution_completed_event,
    'run_completed_event_callback': handle_run_completed_event
}
