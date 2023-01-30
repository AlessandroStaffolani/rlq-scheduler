import time

from rlq_scheduler.common.distributed_queue.base_queue import BaseDistributedQueue
from rlq_scheduler.common.redis_connection import RedisConnectionFactory


class RedisQueue(BaseDistributedQueue):

    def __init__(self, config=None, logger=None):
        super(RedisQueue, self).__init__(config, logger)
        self.redis_connection_factory = RedisConnectionFactory(self.config['connection'])
        self.redis_db = self.config['connection']['db']
        self.redis_connection = self.redis_connection_factory.get_connection()
        self.redis_connection.config_set('notify-keyspace-events', 'KA')

    def push(self, key, value, push_if_not_present=False):
        if push_if_not_present is False:
            return self.redis_connection.rpush(key, value)
        else:
            queue_elements = self.redis_connection.lrange(key, 0, -1)
            if value.encode('utf-8') in queue_elements:
                # No push is performed, because the task_uuid is already present in the queue
                return 0
            else:
                return self.redis_connection.rpush(key, value)

    def get(self, key, timeout=60):
        pub_sub = self.redis_connection.pubsub()
        pub_sub.subscribe(key)
        data = None
        start = time.time()
        while data is None:
            message = pub_sub.get_message(ignore_subscribe_messages=True)
            if message is not None and 'type' in message and message['type'] == 'message':
                data = message['data']
            now = time.time()
            if now - start > timeout:
                raise TimeoutError('No message received on key {} in the latest {} seconds'.format(key, timeout))
            time.sleep(0.001)
        pub_sub.close()
        pub_sub.connection_pool.disconnect()
        return data

    def subscribe(self, key, callback, db=None):
        if db is None:
            db = self.redis_db

        def _internal_callback(message):
            data = message['data'].decode('utf-8')
            if data == 'rpush':
                item = self.redis_connection.lpop(key)
                if item is not None:
                    callback(item.decode('utf-8'))
                else:
                    callback(item)

        pubsub = self.redis_connection.pubsub()
        pubsub.subscribe(**{f'__keyspace@{db}__:{key}': _internal_callback})
        return pubsub.run_in_thread(sleep_time=0.001)

    def close(self):
        self.redis_connection.close()
        self.redis_connection.client().close()
        self.redis_connection.client().connection_pool.disconnect()
