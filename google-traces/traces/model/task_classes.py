import os
from dataclasses import dataclass
from typing import List, Dict, Optional

from pymongo import ASCENDING

from traces import logger, MongoWrapper, mongo_wrapper
from traces.model import EventType
from traces.model.collection_events import CollectionEvent


def _extract_time_structure(time_microseconds: int) -> Dict[str, int]:
    microseconds = 1000000
    days, reminder = divmod(time_microseconds, microseconds * 60 * 60 * 24)
    hours, reminder = divmod(reminder, microseconds * 60 * 60)
    minutes, reminder = divmod(reminder, microseconds * 60)
    seconds, reminder = divmod(reminder, microseconds)
    return {
        'days': days,
        'hours': hours,
        'minutes': minutes,
        'seconds': seconds,
        'microseconds': reminder,
    }


class TimeStructure:

    def __init__(
            self,
            time_microseconds: int
    ):
        self.time_microseconds: int = time_microseconds
        self._time_structure = _extract_time_structure(self.time_microseconds)

    def to_dict(self) -> Dict[str, int]:
        return self._time_structure

    @property
    def days(self) -> int:
        return self._time_structure['days']

    @property
    def hours(self) -> int:
        return self._time_structure['hours']

    @property
    def minutes(self) -> int:
        return self._time_structure['minutes']

    @property
    def seconds(self) -> int:
        return self._time_structure['seconds']

    @property
    def microseconds(self) -> int:
        return self._time_structure['microseconds']

    def __str__(self):
        hours = str(self.hours) if self.hours > 0 else '0'
        minutes = str(self.minutes) if self.minutes > 0 else '00'
        seconds = str(self.seconds) if self.seconds > 0 else '00'
        microseconds = str(self.microseconds) if self.microseconds > 0 else '000000'
        if self.days > 0:
            s = f'{self.days} days, {hours}:{minutes}:{seconds}.{microseconds}'
        else:
            s = f'{hours}:{minutes}:{seconds}.{microseconds}'
        return s


@dataclass
class TaskInstance:
    time_start: Optional[int] = None
    time_end: Optional[int] = None
    max_cpus: Optional[float] = None
    min_cpus: Optional[float] = None
    max_memory: Optional[float] = None
    min_memory: Optional[float] = None

    @property
    def is_completed(self) -> bool:
        return self.time_start is not None and self.time_end is not None

    @property
    def duration(self) -> Optional[int]:
        if self.is_completed:
            return self.time_end - self.time_start
        else:
            return None

    def to_dict(self):
        return {
            'time_start': self.time_start,
            'time_end': self.time_end,
            'duration': self.duration,
            'max_cpus': self.max_cpus,
            'min_cpus': self.min_cpus,
            'max_memory': self.max_memory,
            'min_memory': self.min_memory,
            'time_start_struct': TimeStructure(self.time_start).to_dict(),
            'time_end_struct': TimeStructure(self.time_end).to_dict(),
            'duration_struct': TimeStructure(self.duration).to_dict(),
        }


@dataclass
class TaskClass:
    name: str
    tasks: List[TaskInstance]

    def to_dict(self):
        return {
            'name': self.name,
            'tasks': [instance.to_dict() for instance in self.tasks]
        }


@dataclass
class DatasetRow:
    index: int
    name: str
    time_start: int
    time_end: int
    max_cpus: float
    min_cpus: float
    max_memory: float
    min_memory: float

    @property
    def duration(self):
        return self.time_end - self.time_start

    def to_dict(self):
        return {
            'index': self.index,
            'name': self.name,
            'time_start': self.time_start,
            'time_end': self.time_end,
            'duration': self.duration,
            'max_cpus': self.max_cpus,
            'min_cpus': self.min_cpus,
            'max_memory': self.max_memory,
            'min_memory': self.min_memory,
            'time_start_struct': TimeStructure(self.time_start).to_dict(),
            'time_end_struct': TimeStructure(self.time_end).to_dict(),
            'duration_struct': TimeStructure(self.duration).to_dict(),
        }


collection_events_collection: str = 'collection_events'
instance_events_collection: str = 'instance_events'
task_classes_collection: str = 'task_classes'


class TaskClassInserter:

    def __init__(self):
        self.mongo = MongoWrapper(
            host=os.getenv('MONGO_HOST'),
            port=os.getenv('MONGO_PORT'),
            user=os.getenv('MONGO_USER'),
            db=mongo_wrapper.db_name,
            password=os.getenv('MONGO_PASSWORD')
        )

    def get_job_min_max_resource(self, collection_id: str, resource: str, is_max: bool) -> Optional[float]:
        sort_value = -1 if is_max else 1
        result = self.mongo.db[instance_events_collection]. \
            find({"collection_id": collection_id}).sort([(f'resource_request.{resource}', sort_value)]).limit(1)
        for res in result:
            return res['resource_request'][resource]
        return None

    def get_job_resources(self, collection_id: str):
        max_cpus = self.get_job_min_max_resource(collection_id, resource='cpus', is_max=True)
        min_cpus = self.get_job_min_max_resource(collection_id, resource='cpus', is_max=False)
        max_memory = self.get_job_min_max_resource(collection_id, resource='memory', is_max=True)
        min_memory = self.get_job_min_max_resource(collection_id, resource='memory', is_max=False)

        return max_cpus, min_cpus, max_memory, min_memory

    def process_task_class(self, collection_logical_name: str):
        collection_jobs = self.mongo.db[collection_events_collection].find(
            {'collection_logical_name': collection_logical_name}).sort([('time', 1)])

        jobs: Dict[str, TaskInstance] = {}
        task_class_instances: List[TaskInstance] = []
        # dataset_rows: List[Dict] = []
        for job in collection_jobs:
            collection_event = CollectionEvent(**job)
            if collection_event.collection_id not in jobs:
                jobs[collection_event.collection_id] = TaskInstance(
                    time_start=collection_event.time if collection_event.type == EventType.SCHEDULE else None,
                    time_end=collection_event.time if collection_event.type == EventType.FINISH else None,
                )
            else:
                task_instance = jobs[collection_event.collection_id]
                if collection_event.type == EventType.SCHEDULE:
                    task_instance.time_start = collection_event.time
                if collection_event.type == EventType.FINISH:
                    task_instance.time_end = collection_event.time
                if jobs[collection_event.collection_id].is_completed:
                    max_cpus, min_cpus, max_memory, min_memory = self.get_job_resources(collection_event.collection_id)
                    task_instance.max_cpus = max_cpus
                    task_instance.min_cpus = min_cpus
                    task_instance.max_memory = max_memory
                    task_instance.min_memory = min_memory
                    task_class_instances.append(task_instance)
                    # dataset_rows.append(DatasetRow(
                    #     index=0, name=collection_logical_name,
                    #     time_start=task_instance.time_start,
                    #     time_end=task_instance.time_end,
                    #     max_cpus=max_cpus, min_cpus=min_cpus,
                    #     max_memory=max_memory, min_memory=min_memory
                    # ).to_dict())

        if len(task_class_instances) > 0:
            # we can save the task class
            task_class = TaskClass(name=collection_logical_name, tasks=task_class_instances)
            self.mongo.db[task_classes_collection].insert_one(task_class.to_dict())
            # we can save the dataset row, later on we will update the index
            # self.mongo.db[dataset_collection].insert_many(documents=dataset_rows)


def create_task_classes_index(step: int):
    mongo_wrapper.db[task_classes_collection].create_index([
        ('name', ASCENDING)
    ], background=True, name='task_classes_index')
    logger.info(f'Step {step} | Task Classes and Dataset Pipeline | Created task_classes_index')


def create_dataset_index(dataset_collection_name: str, step: int):
    mongo_wrapper.db[dataset_collection_name].create_index([
        ('index', ASCENDING),
        ('name', ASCENDING),
        ('time_start', ASCENDING),
        ('time_end', ASCENDING),
        ('duration', ASCENDING),
        ('max_cpus', ASCENDING),
        ('min_cpus', ASCENDING),
        ('max_memory', ASCENDING),
        ('min_memory', ASCENDING),
    ], name='dataset_index', background=True)
    logger.info(f'Step {step} | Task Classes and Dataset Pipeline | Created dataset_index')


def extract_dataset(
        n_task_classes: int,
        dataset_collection_name: str,
        step: int,
):
    pipeline = [
        {
            '$unwind': '$tasks'
        }, {
            '$group': {
                '_id': '$_id',
                'task_class': {
                    '$addToSet': '$name'
                },
                'tasks': {
                    '$push': '$tasks'
                },
                'size': {
                    '$sum': 1
                }
            }
        }, {
            '$sort': {
                'size': -1
            }
        }
    ]
    options = {'allowDiskUse': True}
    results = mongo_wrapper.db[task_classes_collection].aggregate(pipeline, **options)
    counter = 1
    dataset_rows = []
    for row in results:
        task_class = f'task_class_{counter}'
        tasks = row['tasks']
        for task in tasks:
            dataset_row = DatasetRow(index=0, name=task_class, time_start=task['time_start'], time_end=task['time_end'],
                                     max_cpus=task['max_cpus'],
                                     min_cpus=task['min_cpus'],
                                     max_memory=task['max_memory'],
                                     min_memory=task['min_memory'],
                                     )
            dataset_rows.append(dataset_row.to_dict())
        if counter + 1 <= n_task_classes:
            counter += 1

        if len(dataset_rows) > 1000:
            mongo_wrapper.db[dataset_collection_name].insert_many(documents=dataset_rows)
            dataset_rows = []
    logger.info(f'Step {step} | Task Classes and Dataset Pipeline |'
                f' Populated tasks_dataset collection')


def update_tasks_dataset_index(dataset_collection_name: str, step: int):
    dataset = mongo_wrapper.db[dataset_collection_name].find({}).sort([('time_start', 1)])
    index_count = 0
    for row in dataset:
        mongo_wrapper.db[dataset_collection_name].update_one({'_id': row['_id']}, {'$set': {'index': index_count}})
        index_count += 1
        if index_count % 2500 == 0:
            logger.info(f'Step {step} | Task Classes and Dataset Pipeline |'
                        f' Updating tasks_dataset indexes, processed {index_count} rows')

