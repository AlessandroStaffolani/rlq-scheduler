from rlq_scheduler.common.system_events.event import SystemStatusChangedEvent, SchedulingStartedEvent, \
    SchedulingCompletedEvent, ExecutionCompletedEvent, StatsUpdateEvent, PrepareNewRunEvent, \
    ResourceStatusChangedEvent, RunCompletedEvent, StartRunEvent, TrajectoryCompletedEvent, RunPhase
from rlq_scheduler.common.utils.decorators import consumer_callback_fetch_exceptions
from rlq_scheduler.system_manager.system_manager import SystemManager, ResourceStatus, SystemStatus
from rlq_scheduler.system_manager.system_manager_context import SystemManagerContext


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_system_status_changed_event(event: SystemStatusChangedEvent, context: SystemManagerContext):
    context.run_manager.system_changed_status(system_status=event.system_status)


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_resource_status_changed_event(event: ResourceStatusChangedEvent, context: SystemManagerContext):
    if event.resource_status == ResourceStatus.NOT_READY and event.resource_name != context.name:
        context.system_producer.publish_resource_status_changed_event(
            resource_name=context.name,
            status=context.status
        )
    if event.resource_status == ResourceStatus.ERROR and event.resource_name == context.name:
        context.system_manager.set_system_status(SystemStatus.ERROR)
    if context.system_manager is not None:
        context.system_manager.resource_has_changed_status(
            resource_name=event.resource_name,
            resource_status=event.resource_status,
            extras=event.extras
        )


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_prepare_new_run_event(event: PrepareNewRunEvent, context: SystemManagerContext):
    if context.previous_run_code is not None:
        context.stats_backend.delete_stats(context.previous_run_code)
    context.logger.run_code = event.new_run_config.run_code
    context.current_run_config = event.new_run_config.config
    context.current_run_code = event.new_run_config.run_code
    context.current_run_stats.run_code = event.new_run_config.run_code
    context.current_run_prepare_time = event.timestamp
    context.trajectory_saver.current_run_code = context.current_run_code
    context.run_manager.current_tasks_executed = 0
    context.system_manager.current_run_code = event.new_run_config.run_code
    context.system_manager.stats_groups = {
        'global_stats': False,
        'agent_stats': False,
        'execution_history_stats': False,
        'tasks_generated': False
    }


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_start_run_event(event: StartRunEvent, context: SystemManagerContext):
    context.logger.info('Staring run with code: {}'.format(event.run_code),
                        resource='SystemManagerContextSystemConsumerCallback')
    context.start_run(start_time=event.timestamp)


# def _handle_resource_ready_event(event: ResourceReadyEvent, context):
#     if event.resource_name not in self.ready_resources:
#         self.ready_resources.append(event.resource_name)
#         self.are_system_resources_ready()


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_stats_updated_event(event: StatsUpdateEvent, context: SystemManagerContext):
    if context.current_run_code != event.run_code:
        context.logger.warning('Received run_code different for the same run. '
                               'Current run_code = {} event run_code = {}'
                               .format(context.current_run_code, event.run_code),
                               resource='SystemManagerContextSystemConsumerCallback')
    system_manager: SystemManager = context.system_manager
    if event.stat_group in system_manager.stats_groups and system_manager.stats_groups[event.stat_group] is False:
        system_manager.stats_groups[event.stat_group] = True
    completed = True
    for _, value in system_manager.stats_groups.items():
        if not value:
            completed = False
    if completed and context.run_manager.is_current_execution_completed:
        context.save_stats_property_value(prop='end_time', value=event.timestamp)
        # save all the stats on disk
        context.save_stats_on_disk()


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_scheduling_started_event(event: SchedulingStartedEvent, context: SystemManagerContext):
    if event.phase == RunPhase.RUN:
        context.run_manager.current_tasks_to_execute = event.task_to_generate
    context.current_phase = event.phase


def handle_trajectory_completed_event(event: TrajectoryCompletedEvent, context: SystemManagerContext):
    if context.current_phase == RunPhase.RUN:
        context.run_manager.current_tasks_executed += 1


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_scheduling_completed_event(event: SchedulingCompletedEvent, context: SystemManagerContext):
    if context.current_phase == RunPhase.RUN:
        if event.task_scheduled != context.run_manager.current_tasks_to_execute:
            context.run_manager.current_tasks_to_execute = \
                event.task_scheduled + context.current_run_config.tasks_to_skip_total()


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_execution_completed_event(event: ExecutionCompletedEvent, context: SystemManagerContext):
    if context.current_phase == RunPhase.RUN:
        context.current_run_end_execution_time = event.timestamp
        # current_tasks_executed + 1 because last task reward is not observed
        if context.run_manager.current_tasks_executed != event.task_executed:
            context.logger.warning('Execution completed but {} tasks have been actually executed while {}'
                                   ' tasks have been scheduled'
                                   .format(context.run_manager.current_tasks_executed,
                                           context.run_manager.current_tasks_to_execute),
                                   resource='SystemManagerContextSystemConsumerCallback')
        context.run_manager.is_current_execution_completed = True
        context.save_stats_property_value(prop='end_execution_time', value=event.timestamp)
        if event.task_executed == context.run_manager.current_tasks_to_execute:
            context.logger.info('Execution completed with success. {} tasks have scheduled and {}'
                                ' tasks have been executed'
                                .format(context.run_manager.current_tasks_to_execute,
                                        context.run_manager.current_tasks_executed),
                                resource='SystemManagerContextSystemConsumerCallback')
        else:
            context.logger.warning('Execution completed but {} tasks have scheduled while {} tasks have been executed'
                                   .format(context.run_manager.current_tasks_to_execute,
                                           event.task_executed),
                                   resource='SystemManagerContextSystemConsumerCallback')
        if not context.trajectory_saver.disabled:
            context.trajectory_saver.flush()
        context.current_phase = RunPhase.WAIT


@consumer_callback_fetch_exceptions(publish_error=True)
def handle_run_completed_event(event: RunCompletedEvent, context: SystemManagerContext):
    context.current_run_end_time = event.timestamp
    context.previous_run_code = context.current_run_code
    context.current_run_code = None
    context.run_manager.executed_runs.append(context.run_manager.current_run)
    context.run_manager.current_run = None


SYSTEM_CONSUMER_CALLBACKS = {
    'generic_event_callback': None,
    'system_status_changed_event_callback': handle_system_status_changed_event,
    'resource_status_changed_event_callback': handle_resource_status_changed_event,
    'prepare_new_run_event_callback': handle_prepare_new_run_event,
    'start_run_event_callback': handle_start_run_event,
    'stats_updated_event_callback': handle_stats_updated_event,
    'scheduling_started_event_callback': handle_scheduling_started_event,
    'trajectory_completed_event_callback': handle_trajectory_completed_event,
    'scheduling_completed_event_callback': handle_scheduling_completed_event,
    'execution_completed_event_callback': handle_execution_completed_event,
    'run_completed_event_callback': handle_run_completed_event
}
