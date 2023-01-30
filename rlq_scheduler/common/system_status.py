import numpy as np

from enum import Enum


class SystemStatus(str, Enum):
    NOT_READY = 'NOT_READY'
    WAITING = 'WAITING'
    READY = 'READY'
    RUNNING = 'RUNNING'
    STOPPED = 'STOPPED'
    ERROR = 'ERROR'


class ResourceStatus(str, Enum):
    NOT_READY = 'NOT_READY'
    WAITING = 'WAITING'
    READY = 'READY'
    RUNNING = 'RUNNING'
    STOPPED = 'STOPPED'
    ERROR = 'ERROR'


def system_status_from_resources_status(
        resource_status_array: dict,
        n_resources: int,
        current_status: SystemStatus) -> SystemStatus:
    if len(resource_status_array[ResourceStatus.ERROR]) > 0:
        return SystemStatus.ERROR
    if len(resource_status_array[ResourceStatus.STOPPED]) > 0:
        return SystemStatus.STOPPED
    if len(resource_status_array[ResourceStatus.NOT_READY]) > 0:
        return SystemStatus.NOT_READY
    if len(resource_status_array[ResourceStatus.WAITING]) == n_resources:
        return SystemStatus.WAITING
    if len(resource_status_array[ResourceStatus.READY]) == n_resources:
        return SystemStatus.READY
    if len(resource_status_array[ResourceStatus.RUNNING]) == n_resources:
        return SystemStatus.RUNNING
    return current_status


def is_resource_ok(resource_status: ResourceStatus):
    ok_status = [
        ResourceStatus.READY,
        ResourceStatus.RUNNING,
        ResourceStatus.WAITING
    ]
    return resource_status in ok_status
