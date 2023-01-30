from rlq_scheduler.common.backends.redis_backend import RedisTrajectoryBackend, RedisBackend


AVAILABLE_BACKEND = {
    'redis': {
        'base': RedisBackend,
        'trajectory': RedisTrajectoryBackend
    }
}


def get_backend_adapter(backend_name, backed_type='base'):
    if backend_name in AVAILABLE_BACKEND:
        return AVAILABLE_BACKEND[backend_name][backed_type]
    else:
        raise AttributeError('The backend required is not valid, use one of {}'.format(AVAILABLE_BACKEND.keys()))
