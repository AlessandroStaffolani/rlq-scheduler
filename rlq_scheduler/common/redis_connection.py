import redis


class RedisConnectionFactory:

    def __init__(self, config=None):
        self.config = config
        self.connection_pool = redis.ConnectionPool(host=self.config['host'], port=self.config['port'],
                                                    db=self.config['db'])

    def get_connection(self):
        return redis.Redis(connection_pool=self.connection_pool)
