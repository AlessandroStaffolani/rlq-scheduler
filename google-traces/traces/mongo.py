import os
from typing import Optional, List, Any, Dict
from urllib.parse import quote_plus

from bson.objectid import ObjectId
from pymongo import MongoClient, UpdateOne
from pymongo.results import InsertOneResult


def get_connection_uri(host, port, password, user, db):
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


class MongoConnector:

    def __init__(
            self,
            host: Optional[str] = None,
            port: Optional[int] = None,
            user: Optional[str] = None,
            db: Optional[str] = None,
            password: Optional[str] = None,
            use_tunnelling: bool = False
    ):
        self.host = host if host is not None else os.getenv('MONGO_HOST')
        self.port = port if port is not None else os.getenv('MONGO_PORT')
        mongo_password = password if password is not None else os.getenv('MONGO_PASSWORD')
        mongo_user = user if user is not None else os.getenv('MONGO_USER')
        self.db_name = db if db is not None else os.getenv('MONGO_DB')
        if use_tunnelling:
            mongo_password = os.getenv('MONGO_PASSWORD_TUNNELLING')
        self.client = MongoClient(
            get_connection_uri(host=self.host, port=self.port, password=mongo_password,
                               user=mongo_user, db=self.db_name),
            serverSelectionTimeoutMS=5000
        )
        self.init()

    def init(self):
        info = self.client.server_info()
        return info

    def close(self):
        self.client.close()


class MongoWrapper(MongoConnector):

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, user: Optional[str] = None,
                 db: Optional[str] = None,
                 password: Optional[str] = None,
                 use_tunnelling: bool = False):
        super(MongoWrapper, self).__init__(host, port, user, db, password, use_tunnelling)
        if self.db_name is not None:
            self.db = self.client[self.db_name]

    def set_db(self, db_name: str):
        if db_name != self.db_name:
            self.db_name = db_name
            self.db = self.client[self.db_name]

    def _populate(self, document, populate_field: str, populate_collection: str, sub_populate=None):
        ids = [db_ref.id for db_ref in document[populate_field]]
        elements = self.get_many(populate_collection, {'_id': {'$in': ids}})

        if sub_populate is not None:
            for elem in elements:
                self._populate(elem,
                               populate_field=sub_populate['field'],
                               populate_collection=sub_populate['collection'],
                               sub_populate=None)
        document[populate_field] = elements

    def save(self, collection: str, document: dict, *args, **kwargs) -> InsertOneResult:
        kwargs = self._set_db(**kwargs)
        return self.db[collection].insert_one(document, *args, **kwargs)

    def get(self, collection, doc_id: str, populate=None, sub_populate=None, *args, **kwargs):
        kwargs = self._set_db(**kwargs)
        result = self.db[collection].find_one({'_id': doc_id}, *args, **kwargs)
        if populate is not None and 'field' in populate and 'collection' in populate:
            self._populate(next(result),
                           populate_field=populate['field'],
                           populate_collection=populate['collection'],
                           sub_populate=sub_populate)
        return result

    def get_by_query(self, collection, query, populate=None, sub_populate=None, *args, **kwargs):
        kwargs = self._set_db(**kwargs)
        result = self.db[collection].find_one(query, *args, **kwargs)
        if populate is not None and 'field' in populate and 'collection' in populate:
            self._populate(result,
                           populate_field=populate['field'],
                           populate_collection=populate['collection'],
                           sub_populate=sub_populate)
        return result

    def get_many(self, collection, query, populate=None, sub_populate=None, return_iterator=False, *args, **kwargs):
        kwargs = self._set_db(**kwargs)
        results = self.db[collection].find(query, *args, **kwargs)
        if return_iterator:
            return results
        return_result = []
        for res in results:
            if populate is not None and 'field' in populate and 'collection' in populate:
                self._populate(res,
                               populate_field=populate['field'],
                               populate_collection=populate['collection'],
                               sub_populate=sub_populate)
            return_result.append(res)
        return return_result

    def update(self, collection, query, update_obj, *args, **kwargs):
        kwargs = self._set_db(**kwargs)
        return self.db[collection].find_one_and_update(query, update_obj, *args, **kwargs)

    def replace(self, collection, query, document, *args, **kwargs):
        kwargs = self._set_db(**kwargs)
        return self.db[collection].find_one_and_replace(query, document, *args, **kwargs)

    def delete(self, collection, doc_id, *args, **kwargs):
        kwargs = self._set_db(**kwargs)
        return self.db[collection].find_one_and_delete({'_id': doc_id}, *args, **kwargs)

    def bulk_save(self, collection, documents, *args, **kwargs):
        kwargs = self._set_db(**kwargs)
        return self.db[collection].insert_many(documents, *args, **kwargs)

    def bulk_update(self, collection, documents, query_param, upsert=False, *args, **kwargs):
        kwargs = self._set_db(**kwargs)
        requests = []
        for doc in documents:
            requests.append(UpdateOne(
                filter={query_param: doc[query_param]},
                update={'$set': doc},
                upsert=upsert
            ))
        return self.db[collection].bulk_write(requests, *args, **kwargs)

    def copy_data_to_collection(self, collection: str, data: List[Dict[str, Any]], keep_id=False):
        docs = []
        for entry in data:
            if '_id' in entry:
                if keep_id:
                    entry['_id'] = ObjectId(entry['_id'])
                else:
                    del entry['_id']
            docs.append(entry)
        self.bulk_save(collection, docs)

    def _set_db(self, **kwargs):
        if 'db' in kwargs:
            self.set_db(kwargs['db'])
            del kwargs['db']
        return kwargs
