import os
from logging import Logger
from urllib.parse import quote_plus

from bson import ObjectId
from pymongo import MongoClient, UpdateOne
from pymongo.errors import ServerSelectionTimeoutError

from rlq_scheduler.common.config_helper import GlobalConfigHelper


def get_connection_uri():
    host = os.getenv('MONGO_HOST')
    port = os.getenv('MONGO_PORT')
    db = os.getenv('MONGO_DB')
    user = os.getenv('MONGO_USER')
    password = os.getenv('MONGO_PASSWORD')
    replica_set = os.getenv('MONGO_REPLICA_SET')
    url = f'mongodb://{host}:{port}/{db}'
    if user is not None and password is not None:
        if user == 'root':
            url = f'mongodb://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}'
        else:
            url = f'mongodb://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{db}'

    if replica_set is not None and len(replica_set) > 0:
        url = f'mongodb://{host}/{db}?replicaSet={replica_set}'
        if user is not None and password is not None:
            if user == 'root':
                url = f'mongodb://{quote_plus(user)}:{quote_plus(password)}@{host}/?replicaSet={replica_set}'
            else:
                url = f'mongodb://{quote_plus(user)}:{quote_plus(password)}@{host}/{db}?replicaSet={replica_set}'

    return url


class DatabaseConnector:

    def __init__(self, global_config: GlobalConfigHelper, logger: Logger):
        self.global_config: GlobalConfigHelper = global_config
        self.logger: Logger = logger
        self.host = os.getenv('MONGO_HOST')
        self.port = os.getenv('MONGO_PORT')
        self.db_name = os.getenv('MONGO_DB')
        self.client = MongoClient(get_connection_uri(), serverSelectionTimeoutMS=10)

    def init(self):
        try:
            info = self.client.server_info()
            self.logger.info('Database connected with success to mongo: {}'.format(info))
            return True
        except ServerSelectionTimeoutError:
            self.logger.error('Impossible to connect Database to mongo using host: {} | port: {} '
                              'and the provided username and password'
                              .format(self.host, self.port))
            return False
        except Exception as e:
            self.logger.exception(e)
            return False

    def close(self):
        self.client.close()
        self.logger.info('Closed connection to MongoDb')


class Database(DatabaseConnector):

    def __init__(self, global_config: GlobalConfigHelper, logger: Logger):
        super(Database, self).__init__(global_config, logger)
        self.db = self.client[self.db_name]

    def _populate(self, document, populate_field: str, populate_collection: str, sub_populate=None):
        ids = [_id for _id in document[populate_field]]
        cursor = self.get_many(populate_collection, {'_id': {'$in': ids}})
        elements = []
        for elem in cursor:
            elements.append(elem)

        if sub_populate is not None:
            for elem in elements:
                self._populate(elem,
                               populate_field=sub_populate['field'],
                               populate_collection=sub_populate['collection'],
                               sub_populate=None)
        document[populate_field] = elements

    def save(self, collection: str, document: dict, *args, **kwargs) -> ObjectId:
        return self.db[collection].insert_one(document, *args, **kwargs)

    def get(self, collection, doc_id: str, populate=None, sub_populate=None, *args, **kwargs):
        result = self.db[collection].find_one({'_id': doc_id}, *args, **kwargs)
        if populate is not None and 'field' in populate and 'collection' in populate:
            self._populate(next(result),
                           populate_field=populate['field'],
                           populate_collection=populate['collection'],
                           sub_populate=sub_populate)
        return result

    def get_by_query(self, collection, query, populate=None, sub_populate=None, *args, **kwargs):
        result = self.db[collection].find_one(query, *args, **kwargs)
        if populate is not None and 'field' in populate and 'collection' in populate:
            self._populate(next(result),
                           populate_field=populate['field'],
                           populate_collection=populate['collection'],
                           sub_populate=sub_populate)
        return result

    def get_many(self, collection, query, populate=None, sub_populate=None, *args, **kwargs):
        results = self.db[collection].find(query, *args, **kwargs)
        if populate is not None and 'field' in populate and 'collection' in populate:
            for res in results:
                self._populate(res,
                               populate_field=populate['field'],
                               populate_collection=populate['collection'],
                               sub_populate=sub_populate)
        return results

    def update(self, collection, query, update_obj, *args, **kwargs):
        return self.db[collection].find_one_and_update(query, update_obj, *args, **kwargs)

    def replace(self, collection, query, document, *args, **kwargs):
        return self.db[collection].find_one_and_replace(query, document, *args, **kwargs)

    def delete(self, collection, doc_id, *args, **kwargs):
        return self.db[collection].find_one_and_delete({'_id': doc_id}, *args, **kwargs)

    def bulk_save(self, collection, documents, *args, **kwargs):
        return self.db[collection].insert_many(documents, *args, **kwargs)

    def bulk_update(self, collection, documents, query_param, upsert=False, *args, **kwargs):
        requests = []
        for doc in documents:
            requests.append(UpdateOne(
                filter={query_param: doc[query_param]},
                update={'$set': doc},
                upsert=upsert
            ))
        return self.db[collection].bulk_write(requests, *args, **kwargs)
