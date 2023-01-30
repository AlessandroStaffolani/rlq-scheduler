from rlq_scheduler.common.distributed_queue.redis_queue import RedisQueue


AVAILABLE_QUEUES = {
    'redis': RedisQueue
}


def get_distributed_queue(queue):
    if queue in AVAILABLE_QUEUES:
        return AVAILABLE_QUEUES[queue]
    else:
        raise AttributeError('The queue required is not valid, use one of {}'.format(AVAILABLE_QUEUES.keys()))
