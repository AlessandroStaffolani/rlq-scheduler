import functools

from rlq_scheduler.common.system_events.event import Event
from rlq_scheduler.common.system_events.producer import SystemEventProducer
from rlq_scheduler.common.system_status import ResourceStatus


def class_fetch_exceptions(publish_error=False, is_context=False, producer_property='system_producer'):
    def outer_wrapper_function(func):
        @functools.wraps(func)
        def inner_wrapper_function(self, *args, **kwargs):
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                self.logger.exception(e)
                if publish_error is True and is_context is True:
                    producer: SystemEventProducer = getattr(self, producer_property)
                    if producer is not None:
                        producer.publish_resource_status_changed_event(
                            resource_name=self.name,
                            status=ResourceStatus.ERROR)

        return inner_wrapper_function

    return outer_wrapper_function


def consumer_callback_fetch_exceptions(publish_error=False, producer_property='system_producer'):
    def outer_wrapper_function(func):
        @functools.wraps(func)
        def inner_wrapper_function(event: Event, context, *args, **kwargs):
            try:
                return func(event, context, *args, **kwargs)
            except Exception as e:
                context.logger.exception(e)
                if publish_error is True:
                    producer: SystemEventProducer = getattr(context, producer_property)
                    if producer is not None:
                        producer.publish_resource_status_changed_event(
                            resource_name=context.name,
                            status=ResourceStatus.ERROR)

        return inner_wrapper_function

    return outer_wrapper_function


def retry_on_exceptions(max_retries, exceptions):
    def outer_wrapper_function(func):
        @functools.wraps(func)
        def inner_wrapper_function(self, *args, **kwargs):
            for retries in range(max_retries):
                try:
                    return func(self, *args, **kwargs)
                except exceptions:
                    if self.logger is not None:
                        self.logger.warning(
                            'Error while executing {}, retrying to execute operation.'
                            ' Max retries = {} current retries = {}'
                                .format(func.__name__, max_retries, retries))
                except Exception as e:
                    if self.logger is not None:
                        self.logger.exception(e)
                        return None

        return inner_wrapper_function

    return outer_wrapper_function
