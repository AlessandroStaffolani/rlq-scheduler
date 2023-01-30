import json
import os
from threading import Lock
from typing import List, Optional, Dict

from pymongo import ASCENDING, TEXT

from traces import logger, mongo_wrapper, MongoWrapper
from traces.downloader import TableNames, FileInfo
from traces.filesystem import get_file_len
from traces.hash_utils import make_hash
from traces.model import EventType


class CollectionEvent:
    table_name: TableNames = TableNames.CollectionEvent

    def __init__(
            self,
            collection_logical_name: str,
            collection_id: str,
            type: str,
            time: str,
            max_per_machine: Optional[int] = None,
            **kwargs
    ):
        self.time: int = int(time)
        self.type: EventType = EventType(type)
        self.collection_logical_name: str = collection_logical_name
        self.collection_id: str = collection_id
        self.max_per_machine: Optional[int] = max_per_machine

    def to_dict(self, no_hash: bool = False):
        dict_collection = {
            'time': self.time,
            'type': self.type,
            'collection_id': self.collection_id,
            'collection_logical_name': self.collection_logical_name,
            'max_per_machine': self.max_per_machine
        }
        if no_hash is True:
            return dict_collection
        dict_collection['hash'] = hash(self)
        return dict_collection

    def __hash__(self):
        return make_hash(self.to_dict(no_hash=True))

    # def save(self):
    #     search = self.mongo.get_by_query(
    #         collection=self.table_name.value,
    #         query={'collection_logical_name': self.collection_logical_name}
    #     )
    #     if search is None:
    #         self.mongo.save(collection=self.table_name.value, document=self.to_dict())
    #     else:
    #         old_unique_ids = search['unique_ids']
    #         self.mongo.update(
    #             collection=self.table_name.value,
    #             query={'collection_logical_name': self.collection_logical_name},
    #             update_obj={'$set': {'unique_ids': old_unique_ids + self.unique_ids}}
    #         )
    #     self.unique_ids = []


class CollectionEventInserter:

    def __init__(self, valid_max_per_machine: str = '1'):
        self.mongo = MongoWrapper(
            host=os.getenv('MONGO_HOST'),
            port=os.getenv('MONGO_PORT'),
            user=os.getenv('MONGO_USER'),
            db=mongo_wrapper.db_name,
            password=os.getenv('MONGO_PASSWORD')
        )
        self.valid_max_per_machine: Optional[str] = valid_max_per_machine if valid_max_per_machine != "" else None
        self.ignored_collections = 0
        self.saved_collections = 0
        self.collections: List[CollectionEvent] = []

    def append(
            self,
            collection_logical_name: str,
            collection_id: str,
            type: str,
            parent_collection_id: Optional[str] = None,
            max_per_machine: Optional[str] = None,
            **kwargs,
    ):
        if parent_collection_id is None and EventType.is_an_accepted_type(type):
            if self.valid_max_per_machine is not None:
                if max_per_machine == self.valid_max_per_machine:
                    self.collections.append(
                        CollectionEvent(
                            collection_logical_name=collection_logical_name,
                            collection_id=collection_id,
                            type=type,
                            parent_collection_id=parent_collection_id,
                            max_per_machine=max_per_machine,
                            **kwargs
                        )
                    )
            else:
                self.collections.append(
                    CollectionEvent(
                        collection_logical_name=collection_logical_name,
                        collection_id=collection_id,
                        type=type,
                        parent_collection_id=parent_collection_id,
                        max_per_machine=max_per_machine,
                        **kwargs
                    )
                )
        else:
            self.ignored_collections += 1

    def get_documents_to_insert(self) -> List[dict]:
        documents = []
        for collection in self.collections:
            search = self.mongo.get_many(collection=TableNames.CollectionEvent, query={'hash': hash(collection)})
            if len(search) == 0:
                # unique hash, we will insert this
                documents.append(collection.to_dict())
        return documents

    def save(self):
        if len(self.collections) > 0:
            try:
                documents = self.get_documents_to_insert()
                if len(documents) > 0:
                    self.mongo.bulk_save(
                        collection=TableNames.CollectionEvent,
                        documents=documents
                    )
                    self.saved_collections += len(documents)
            except Exception as e:
                logger.error('Error while inserting batch of collection events')
                logger.exception(e)


def extract_unique_jobs(output_path: str, file_info: FileInfo, step: int, max_per_machine: str):
    count = 0
    unzipped_path = os.path.join(output_path, file_info.unzipped_name)
    collection_inserter = CollectionEventInserter(valid_max_per_machine=max_per_machine)
    file_lines = get_file_len(unzipped_path)
    with open(unzipped_path) as file:
        for line in file:
            row_data = json.loads(line)
            collection_inserter.append(**row_data)
            count += 1
            if count % (file_lines // 4) == 0:
                logger.debug(f'Step {step} | Collection Events Pipeline |'
                             f' still looking for unique jobs | processing line {count}/{file_lines}')

    collection_inserter.save()
    logger.info(f'Step {step} | Collection Events Pipeline | saved {collection_inserter.saved_collections} '
                f'and ignored {collection_inserter.ignored_collections} collection events')


def create_collection_events_hash_index(step: int):
    mongo_wrapper.db[TableNames.CollectionEvent].create_index([
        ('hash', ASCENDING)], background=True, name='collection_events_hash')
    logger.info(f'Step {step} | Collection Events Pipeline | '
                f'Created collection_events_hash index')


def create_collection_events_indexes(step: int):
    mongo_wrapper.db[TableNames.CollectionEvent].create_index([
        ('time', ASCENDING),
        ('type', ASCENDING),
        ('collection_id', ASCENDING),
        ('collection_logical_name', ASCENDING),
        ('max_per_machine', ASCENDING),
    ], background=True, name='collection_events_index')
    mongo_wrapper.db[TableNames.CollectionEvent].create_index([
        ('collection_id', TEXT),
        ('collection_logical_name', TEXT),
    ], background=True, name='collection_events_search_index')
    logger.info(f'Step {step} | Collection Events Pipeline | '
                f'Created collection_events_index and collection_events_search_index indexes')


def get_collection_events_unique_ids(step: int) -> Dict[str, str]:
    ids = {}
    collections = mongo_wrapper.get_many(collection=TableNames.CollectionEvent.value, query={}, return_iterator=True)
    for doc in collections:
        collection_id = doc['collection_id']
        if collection_id not in ids:
            ids[collection_id] = doc['collection_logical_name']
    return ids


def get_unique_collections() -> List[str]:
    collections_list = []
    result = mongo_wrapper.db[TableNames.CollectionEvent].aggregate([
        {
            '$group': {
                '_id': {
                    'collection_logical_name': '$collection_logical_name'
                },
                'count': {
                    '$sum': 1
                }
            }
        }, {
            '$sort': {
                'time': 1
            }
        }
    ])

    for row in result:
        collections_list.append(row['_id']['collection_logical_name'])

    return collections_list


def count_jobs_types_single_file(output_path: str, file_info: FileInfo, step: int, stats: Dict[str, int], lock: Lock):
    try:
        internal_stats = {
            'isolated': 0,  # no relationship and max_per_machine = 1
            'no_relationship': 0,  # no relationship -> no parent jobs and no start_after_collection_ids
            'children': 0,  # jobs with a parent job
            'sequential': 0,  # jobs with at least one start_after_collection_ids
        }
        count = 0
        unzipped_path = os.path.join(output_path, file_info.unzipped_name)
        file_lines = get_file_len(unzipped_path)
        with open(unzipped_path) as file:
            for line in file:
                row_data = json.loads(line)
                event_type = EventType(row_data['type'])
                if event_type.FINISH:
                    if _is_isolated_job(**row_data):
                        # if isolated can't be of any other type
                        internal_stats['isolated'] += 1
                    elif _is_no_relationship_job(**row_data):
                        # if no_relationship can't be of any other type
                        internal_stats['no_relationship'] += 1
                    else:
                        # it can be both children and sequential
                        if _is_children_job(**row_data):
                            internal_stats['children'] += 1
                        if _is_sequential_job(**row_data):
                            internal_stats['sequential'] += 1
                count += 1
                if count % (file_lines // 4) == 0:
                    logger.debug(f'Step {step} | Count Jobs Types |'
                                 f' still counting jobs types | processing line {count}/{file_lines}')
        logger.debug(f'Step {step} | Count Jobs Types | file stats: {internal_stats}')
        with lock:
            for key, value in internal_stats.items():
                stats[key] += value
    except Exception as e:
        logger.exception(e)
        raise e


def _is_isolated_job(
        parent_collection_id: Optional[str] = None,
        max_per_machine: Optional[str] = None,
        start_after_collection_ids: [List[str]] = [],
        **kwargs
) -> bool:
    return parent_collection_id is None and max_per_machine == '1' and len(start_after_collection_ids) == 0


def _is_no_relationship_job(
        parent_collection_id: Optional[str] = None,
        start_after_collection_ids: [List[str]] = [],
        **kwargs
) -> bool:
    return parent_collection_id is None and len(start_after_collection_ids) == 0


def _is_children_job(parent_collection_id: Optional[str] = None, **kwargs) -> bool:
    return parent_collection_id is not None


def _is_sequential_job(start_after_collection_ids: [List[str]] = [], **kwargs) -> bool:
    return len(start_after_collection_ids) > 0
