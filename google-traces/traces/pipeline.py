import os
import time
from multiprocessing.pool import ThreadPool
from threading import Lock
from typing import Dict

from traces import logger, mongo_wrapper
from traces.downloader import FileInfo, TableInfo, download_call
from traces.filesystem import get_absolute_path, create_directory, save_file
from traces.model.collection_events import extract_unique_jobs, \
    create_collection_events_indexes, create_collection_events_hash_index, get_unique_collections, \
    count_jobs_types_single_file
from traces.model.instance_events import extract_instance_events, create_instance_events_indexes, \
    create_instance_events_hash_index
from traces.model.paper_classes import get_task_and_worker_classes
from traces.model.task_classes import TaskClassInserter, create_dataset_index, create_task_classes_index, \
    update_tasks_dataset_index, extract_dataset


def collection_events_pipeline(
        output: str,
        table_info: TableInfo,
        parallel: int = 1,
        max_per_machine: str = '1',
        step: int = 2
):
    logger.info(f'Step {step} | Collection Events Pipeline | Starting using {parallel} parallel workers')
    output_path = get_absolute_path(output)
    create_directory(output_path)
    pool = ThreadPool(processes=parallel)
    for i in range(table_info.number):
        pool.apply_async(_collection_events_pipeline,
                         kwds={
                             'output_path': output_path,
                             'file_info': table_info.files[i],
                             'index': i,
                             'total': table_info.number,
                             'step': step,
                             'max_per_machine': max_per_machine
                         },
                         error_callback=lambda err: logger.exception(err))
    pool.close()
    pool.join()


def _collection_events_pipeline(
        output_path: str,
        file_info: FileInfo,
        index: int,
        total: int,
        step: int,
        max_per_machine: str,
):
    # download and unzip next file
    logger.info(f'Step {step} | Collection Events Pipeline | Downloading file {index + 1}/{total}')
    download_call(file_info.path, output_path, file_info.unzipped_name)
    logger.info(f'Step {step} | Collection Events Pipeline | looking for unique jobs')
    # look for unique collections and store information
    create_collection_events_hash_index(step)
    extract_unique_jobs(output_path, file_info, step, max_per_machine)
    create_collection_events_indexes(step)
    # clean up, remove the file
    logger.info(
        f'Step {step} | Collection Events Pipeline | pipeline for file {index + 1}/{total} completed, cleaning up')
    os.remove(os.path.join(output_path, file_info.unzipped_name))


def instance_events_pipeline(
        output: str,
        table_info: TableInfo,
        parallel: int = 1,
        step: int = 2
):
    logger.info(f'Step {step} | Instance Events Pipeline | Starting using {parallel} parallel workers')
    output_path = get_absolute_path(output)
    create_directory(output_path)
    pool = ThreadPool(processes=parallel)
    for i in range(table_info.number):
        pool.apply_async(_instance_events_pipeline,
                         kwds={
                             'output_path': output_path,
                             'file_info': table_info.files[i],
                             'index': i,
                             'total': table_info.number,
                             'step': step,
                         },
                         error_callback=lambda err: logger.exception(err))
        time.sleep(10)
    pool.close()
    pool.join()
    logger.info(f'Step {step} | Instance Events Pipeline | Completed with success')


def _instance_events_pipeline(
        output_path: str,
        file_info: FileInfo,
        index: int,
        total: int,
        step: int,
):
    # download and unzip next file
    logger.info(f'Step {step} | Instance Events Pipeline | Downloading file {index + 1}/{total}')
    download_call(file_info.path, output_path, file_info.unzipped_name)
    logger.info(f'Step {step} | Instance Events Pipeline | looking for instance events from saved collection events')
    create_instance_events_hash_index(step)
    extract_instance_events(output_path, file_info, step)
    create_instance_events_indexes(step)
    # clean up, remove the file
    logger.info(
        f'Step {step} | Instance Events Pipeline | pipeline for file {index + 1}/{total} completed, cleaning up')
    os.remove(os.path.join(output_path, file_info.unzipped_name))


def task_and_worker_classes_pipeline(
        output_path: str,
        max_per_machine: str,
        event_type: str,
        step: int,
):
    logger.info(f'Step {step} | Task and worker classes')
    task_classes, worker_classes_attributes = get_task_and_worker_classes(
        max_per_machine=max_per_machine, logger_prefix=f'Step {step} | Task and worker classes', event_type=event_type)
    save_file(output_path, 'task_classes.json', task_classes, sort_keys=True, indent=2)
    save_file(output_path, 'worker_classes.json', worker_classes_attributes, sort_keys=True, indent=2)


def task_classes_and_dataset_pipeline(
        parallel: int = 1,
        step: int = 4
):
    logger.info(f'Step {step} | Task Classes and Dataset Pipeline | Starting using {parallel} parallel workers')
    pool = ThreadPool(processes=parallel)
    unique_collections = get_unique_collections()
    n_collections = len(unique_collections)
    for i, collection_logical_name in enumerate(unique_collections):
        pool.apply_async(_task_classes_and_dataset_pipeline,
                         kwds={
                             'collection_logical_name': collection_logical_name,
                             'index': i,
                             'n_collections': n_collections,
                             'step': step
                         },
                         error_callback=lambda err: logger.exception(err))

    pool.close()
    pool.join()
    create_task_classes_index(step)
    logger.info(f'Step {step} | Task Classes and Dataset Pipeline | Completed with success')


def _task_classes_and_dataset_pipeline(
        collection_logical_name: str,
        index: int,
        n_collections: int,
        step: int
):
    task_class_inserter = TaskClassInserter()
    task_class_inserter.process_task_class(collection_logical_name)
    if index % (n_collections // 4) == 0 or index == 0:
        logger.info(f'Step {step} | Task Classes and Dataset Pipeline |'
                    f' processed collections {index + 1}/{n_collections}')


def extract_dataset_pipeline(
        n_task_classes: int,
        dataset_collection_name: str,
        step: int = 5
):
    logger.info(f'Step {step} | Task Classes and Dataset Pipeline | Extracting dataset')
    create_dataset_index(dataset_collection_name, step)
    extract_dataset(n_task_classes, dataset_collection_name, step)
    update_tasks_dataset_index(dataset_collection_name, step)
    logger.info(f'Step {step} | Task Classes and Dataset Pipeline | Dataset extracted with success')


def count_jobs_types(
        output_path: str,
        table_info: TableInfo,
        parallel: int = 4,
        step: int = 6
):
    logger.info(f'Step {step} | Count Jobs Types | Starting using {parallel} parallel workers')
    pool = ThreadPool(processes=parallel)
    lock = Lock()
    stats = {
        'isolated': 0,  # no relationship and max_per_machine = 1
        'no_relationship': 0,  # no relationship -> no parent jobs and no start_after_collection_ids
        'children': 0,  # jobs with a parent job
        'sequential': 0,  # jobs with at least one start_after_collection_ids
    }
    for i in range(table_info.number):
        pool.apply_async(_count_jobs_types,
                         kwds={
                             'output_path': output_path,
                             'file_info': table_info.files[i],
                             'index': i,
                             'stats': stats,
                             'total': table_info.number,
                             'step': step,
                             'lock': lock
                         },
                         error_callback=lambda err: logger.exception(err))
    pool.close()
    pool.join()
    save_file(output_path, 'job_types.json', stats, sort_keys=True, indent=2)
    mongo_wrapper.db['job_types'].insert_one(stats)
    logger.info(f'Step {step} | Count Jobs Types | Completed with success')


def _count_jobs_types(
        output_path: str,
        file_info: FileInfo,
        index: int,
        stats: Dict[str, int],
        total: int,
        step: int,
        lock: Lock
):
    logger.info(f'Step {step} | Count Jobs Types | Downloading file {index + 1}/{total}')
    download_call(file_info.path, output_path, file_info.unzipped_name)
    logger.info(f'Step {step} | Collection Events Pipeline | looking for unique jobs')
    count_jobs_types_single_file(output_path, file_info, step, stats, lock)
    logger.info(
        f'Step {step} | Count Jobs Types | pipeline for file {index + 1}/{total} completed, cleaning up')
    os.remove(os.path.join(output_path, file_info.unzipped_name))
