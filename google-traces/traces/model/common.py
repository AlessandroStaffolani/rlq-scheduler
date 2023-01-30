import os.path
from typing import Optional

from pymongo import ASCENDING
from tqdm import tqdm

from traces import mongo_wrapper
from traces.filesystem import save_file


def clean_duplicates(collection_name: str):
    print(f'Cleaning {collection_name} duplicates')
    mongo_wrapper.db[collection_name].create_index(
        [('cleaned', ASCENDING)], background=True, name=f'{collection_name}_cleaned_index')
    pipeline = [
        {
            '$match': {
                'cleaned': {
                    '$exists': False
                }
            }
        }, {
            '$group': {
                '_id': {
                    'hash': '$hash'
                },
                'dups': {
                    '$push': {
                        '_id': '$_id'
                    }
                },
                'count': {
                    '$sum': 1
                }
            }
        }, {
            '$match': {
                'count': {
                    '$gt': 1
                }
            }
        }
    ]
    duplicates_cursor = mongo_wrapper.db[collection_name].aggregate(pipeline, allowDiskUse=True)
    ids_to_remove = []
    ids_cleaned = []
    n_duplicates = 0
    with tqdm(duplicates_cursor,
              desc=f'found {n_duplicates} duplicates while processing {collection_name} documents',
              unit='duplicates') as t:
        for duplicate in t:
            ids_cleaned.append(duplicate['dups'][0]['_id'])
            for dup in duplicate['dups'][1:]:
                ids_to_remove.append(dup['_id'])
                n_duplicates += 1
                t.set_description(
                    f'found {n_duplicates} duplicates while processed {collection_name} documents')

    if len(ids_to_remove) > 0:
        mongo_wrapper.db[collection_name].delete_many({'_id': {"$in": ids_to_remove}})
    if len(ids_cleaned) > 0:
        mongo_wrapper.db[collection_name].update_many({'_id': {'$in': ids_cleaned}}, {'$set': {"cleaned": True}})
    print(f'Removed {n_duplicates} duplicated {collection_name}')


def _clean_duplicates(collection_name: str, n_duplicates: int):
    mongo_wrapper.db[collection_name].create_index(
        [('cleaned', ASCENDING)], background=True, name=f'{collection_name}_cleaned_index')
    documents = mongo_wrapper.db[collection_name].find({"cleaned": {"$ne": True}})
    i = 0
    cleaned_ids = []
    to_remove_ids = []
    with tqdm(documents,
              desc=f'found {n_duplicates} duplicates while processing {collection_name} documents', unit='docs') as t:
        for doc in t:
            # search = [res for res in mongo_wrapper.db[collection_name].find({'hash': doc['hash']})]
            search_count = mongo_wrapper.db[collection_name].count_documents({'hash': doc['hash']})
            if search_count > 1:
                search = mongo_wrapper.db[collection_name].find({'hash': doc['hash']})
                for e in search:
                    if e['_id'] != doc['_id']:
                        to_remove_ids.append(e['_id'])
                        n_duplicates += 1
                        t.set_description(
                            f'found {n_duplicates} duplicates while processed {collection_name} documents')
            cleaned_ids.append(doc['_id'])
            i += 1
            if len(cleaned_ids) > 1000:
                # mongo_wrapper.db[collection_name].update_many(
                #     {'_id': {'$in': cleaned_ids}}, {'$set': {"cleaned": True}})
                cleaned_ids = []
                # print(f'Processed {collection_name} documents:\t{i}\t\tfound {n_cleaned} duplicates', end='\r')
            if len(to_remove_ids) > 1000:
                # mongo_wrapper.db[collection_name].delete_many({'_id': {"$in": to_remove_ids}})
                # mongo_wrapper.db[collection_name].update_many(
                #     {'_id': {'$in': cleaned_ids}}, {'$set': {"cleaned": True}})
                return _clean_duplicates(collection_name, n_duplicates)
    # mongo_wrapper.db[collection_name].delete_many({'_id': {"$in": to_remove_ids}})
    return n_duplicates


def export_dataset(dataset_collection: str, time_scaling_factor: int, output: str, indent: Optional[int] = None):
    indexes = {}
    documents = [doc for doc in mongo_wrapper.db[dataset_collection].find({'duration': {'$gt': 1}}).sort([('index', 1)])]

    for i, doc in enumerate(documents):
        if i+1 < len(documents):
            next_doc = documents[i+1]
            next_task_start = next_doc['time_start'] - doc['time_start']
        else:
            next_task_start = 0
        indexes[doc['index']] = {
            'task_class': doc['name'],
            'duration': doc['duration'] / time_scaling_factor,
            'next_task_start': next_task_start / time_scaling_factor
        }
    output_parts = output.split('/')
    save_file(
        path=os.path.join(*output_parts[:-1]), filename=output_parts[-1],
        content=indexes, indent=indent,
    )
