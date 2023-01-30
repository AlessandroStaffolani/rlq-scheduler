from typing import Dict, Any, Tuple, Optional

from traces import mongo_wrapper, logger
from traces.downloader import TableNames


def get_task_and_worker_classes(
        max_per_machine: str = '1',
        logger_prefix: str = '',
        event_type: Optional[str] = None
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, float]]]:
    join_equals = [
        {'$eq': ['$collection_logical_name', '$$collection_logical_name']}
    ]
    if event_type is not None:
        join_equals.append({'$eq': ['$type', event_type]})
    pipeline = [
        {
            '$match': {
                '$expr': {
                    '$eq': [
                        '$max_per_machine', max_per_machine
                    ]
                }
            }
        },
        {
            '$lookup': {
                'from': 'instance_events',
                'let': {
                    'collection_logical_name': '$collection_logical_name'
                },
                'pipeline': [
                    {
                        '$match': {
                            '$expr': {
                                '$and': join_equals
                            }
                        }
                    }, {
                        '$unwind': {
                            'path': '$resource_request',
                            'preserveNullAndEmptyArrays': True
                        }
                    }, {
                        '$group': {
                            '_id': {
                                'collection_logical_name': '$collection_logical_name'
                            },
                            'cpus_max': {
                                '$max': '$resource_request.cpus'
                            },
                            'cpus_min': {
                                '$min': '$resource_request.cpus'
                            },
                            'memory_max': {
                                '$max': '$resource_request.memory'
                            },
                            'memory_min': {
                                '$min': '$resource_request.memory'
                            },
                            'n_tasks': {
                                '$sum': 1
                            }
                        }
                    }
                ],
                'as': 'instance_event'
            }
        }
    ]
    options = {'allowDiskUse': True}
    logger.info(f'{logger_prefix} | Calling aggregate query, it might take a while for executing')
    result = mongo_wrapper.db[TableNames.CollectionEvent.value].aggregate(pipeline, **options)
    logger.info(f'{logger_prefix} | Aggregate query results obtained, starting final processing')
    task_classes: Dict[str, Dict[str, Any]] = {}
    overall_cpu_max, overall_cpu_min = 0, 1
    overall_memory_max, overall_memory_min = 0, 1

    count = 1

    for row in result:
        if count % 200 == 0:
            logger.debug(f'{logger_prefix} | processing row {count}')
        count += 1
        if row["max_per_machine"] == max_per_machine:
            if len(row['instance_event']) > 0:
                instance_event = row['instance_event'][0]
                task_classes[row['collection_logical_name']] = {
                    'n_tasks': instance_event['n_tasks'],
                    'cpus': {
                        'min': instance_event['cpus_min'],
                        'max': instance_event['cpus_max']
                    },
                    'memory': {
                        'min': instance_event['memory_min'],
                        'max': instance_event['memory_max']
                    }
                }
                if instance_event['cpus_min'] < overall_cpu_min:
                    overall_cpu_min = instance_event['cpus_min']

                if instance_event['cpus_max'] > overall_cpu_max:
                    overall_cpu_max = instance_event['cpus_max']

                if instance_event['memory_min'] < overall_memory_min:
                    overall_memory_min = instance_event['memory_min']

                if instance_event['memory_max'] > overall_memory_max:
                    overall_memory_max = instance_event['memory_max']
            else:
                logger.warning(
                    f'{logger_prefix} | collection {row["collection_logical_name"]}'
                    f' has no instance event in the dataset')
        else:
            logger.warning(
                f'{logger_prefix} | collection {row["collection_logical_name"]} '
                f'has attribute max_per_machine = {row["max_per_machine"]}')

    return task_classes, {
        'cpus': {
            'min': overall_cpu_min,
            'max': overall_cpu_max,
        },
        'memory': {
            'min': overall_memory_min,
            'max': overall_memory_max,
        }
    }
