from enum import Enum


class EventType(str, Enum):
    SUBMIT = 0
    QUEUE = 1
    ENABLE = 2
    SCHEDULE = 3
    EVICT = 4
    FAIL = 5
    FINISH = 6
    KILL = 7
    LOST = 8
    UPDATE_PENDING = 9
    UPDATE_RUNNING = 10

    @staticmethod
    def is_an_accepted_type(check_type: str):
        accepted_types = [EventType.SCHEDULE, EventType.FINISH, EventType.UPDATE_RUNNING]
        return EventType(check_type) in accepted_types
