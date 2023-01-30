import json
import os
from typing import Dict, Any, List

from pymongo import ASCENDING, TEXT
from pymongo.errors import BulkWriteError

from traces import logger, mongo_wrapper, MongoWrapper
from traces.downloader import TableNames, FileInfo
from traces.filesystem import get_file_len
from traces.hash_utils import make_hash
from traces.model import EventType
from traces.model.collection_events import get_collection_events_unique_ids


class InstanceEvent:
    table_name: TableNames = TableNames.InstanceEvent

    def __init__(
            self,
            collection_logical_name,
            collection_id,
            **data
    ):
        self.time: int = int(data['time'] if 'time' in data else 0)
        self.type: EventType = EventType(data['type'] if 'type' in data else None)
        self.collection_logical_name: str = collection_logical_name
        self.collection_id: str = collection_id
        self.instance_index: int = data['instance_index'] if 'instance_index' in data else 0
        self.resource_request: Dict[str, float] = data['resource_request'] if 'resource_request' in data else {
            'cpus': None, 'memory': None}

    def to_dict(self, no_hash: bool = False) -> Dict[str, Any]:
        dict_instance ={
            'time': self.time,
            'type': self.type,
            'collection_logical_name': self.collection_logical_name,
            'collection_id': self.collection_id,
            'instance_index': self.instance_index,
            'resource_request': self.resource_request
        }
        if no_hash is True:
            return dict_instance
        dict_instance['hash'] = hash(self)
        return dict_instance

    def __hash__(self):
        return make_hash(self.to_dict(no_hash=True))


class InstanceEventInserter:

    def __init__(self, step: int):
        self.mongo = MongoWrapper(
            host=os.getenv('MONGO_HOST'),
            port=os.getenv('MONGO_PORT'),
            user=os.getenv('MONGO_USER'),
            db=mongo_wrapper.db_name,
            password=os.getenv('MONGO_PASSWORD')
        )
        self.ignored_instances = 0
        self.saved_instances = 0
        self.instances: List[InstanceEvent] = []
        self.collection_ids: Dict[str, str] = get_collection_events_unique_ids(step)

    def append(
            self,
            collection_type: str,
            collection_id: str,
            type: str,
            **kwargs
    ):
        # check that collection type is 0 (is a job) and
        # check that the collection_id is in the list of collection_id from mongo
        if collection_type == '0' and collection_id in self.collection_ids and EventType.is_an_accepted_type(type):
            self.instances.append(
                InstanceEvent(
                    collection_id=collection_id,
                    collection_logical_name=self.collection_ids[collection_id],
                    type=type,
                    **kwargs
                )
            )
        else:
            self.ignored_instances += 1
        if len(self.instances) > 10000:
            self.save()

    def get_documents_to_insert(self) -> List[dict]:
        documents = []
        for instance in self.instances:
            search = self.mongo.get_many(collection=TableNames.InstanceEvent, query={'hash': hash(instance)})
            if len(search) == 0:
                # unique hash, we will insert this
                documents.append(instance.to_dict())
        return documents

    def save(self):
        if len(self.instances) > 0:
            try:
                documents = self.get_documents_to_insert()
                if len(documents) > 0:
                    self.mongo.bulk_save(
                        collection=TableNames.InstanceEvent,
                        documents=self.get_documents_to_insert()
                    )
                    self.saved_instances += len(documents)
                    self.instances = []
            except BulkWriteError as e:
                panic = list(filter(lambda x: x['code'] != 11000, e.details['writeErrors']))
                if len(panic) > 0:
                    logger.error('Error while inserting batch of instance events')
                    logger.exception(e)


def extract_instance_events(
        output_path: str,
        file_info: FileInfo,
        step: int
):
    count = 0
    unzipped_path = os.path.join(output_path, file_info.unzipped_name)
    instance_inserter = InstanceEventInserter(step)
    file_lines = get_file_len(unzipped_path)
    with open(unzipped_path) as file:
        for line in file:
            row_data = json.loads(line)
            instance_inserter.append(**row_data)
            count += 1
            if count % (file_lines // 4) == 0:
                logger.debug(f'Step {step} | Instance Events Pipeline |'
                             f' still extracting instance events | processing line {count}/{file_lines}')

    instance_inserter.save()
    logger.info(f'Step {step} | Instance Events Pipeline | saved {instance_inserter.saved_instances} '
                f'and ignored {instance_inserter.ignored_instances} instance events')


def create_instance_events_hash_index(step: int):
    mongo_wrapper.db[TableNames.InstanceEvent].create_index([
        ('hash', ASCENDING)], background=True, name='instance_events_hash')
    logger.info(f'Step {step} | Instance Events Pipeline | '
                f'Created instance_events_hash index')


def create_instance_events_indexes(step: int):
    mongo_wrapper.db[TableNames.InstanceEvent].create_index([
        ('time', ASCENDING),
        ('type', ASCENDING),
        ('collection_id', ASCENDING),
        ('instance_index', ASCENDING),
        ('collection_logical_name', ASCENDING),
        ('resource_request', ASCENDING),
    ], background=True, name='instance_events_index')
    mongo_wrapper.db[TableNames.InstanceEvent].create_index([
        ('collection_id', TEXT),
        ('collection_logical_name', TEXT),
    ], background=True, name='instance_events_search_index')
    logger.info(f'Step {step} | Instance Events Pipeline | '
                f'Created instance_events_index and instance_events_search_index indexes')
