import os.path
import subprocess
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Union, List, Dict
from multiprocessing.pool import ThreadPool

from traces import logger
from traces.filesystem import sizeof_fmt, create_directory, get_absolute_path


class TableNames(str, Enum):
    CollectionEvent = 'collection_events'
    InstanceEvent = 'instance_events'
    InstanceUsage = 'instance_usage'
    MachineAttribute = 'machine_attributes'
    MachineEvent = 'machine_events'


@dataclass
class FileInfo:
    path: str
    size: int
    created_at: datetime

    @property
    def name(self):
        return self.path.split('/')[-1]

    @property
    def unzipped_path(self):
        if self.path.endswith('.gz'):
            return self.path[:-3]
        else:
            return self.path

    @property
    def unzipped_name(self):
        if self.name.endswith('.gz'):
            return self.name[:-3]
        else:
            return self.name

    @property
    def table_name(self):
        return TableNames(self.name.split('-')[0])

    @property
    def human_size(self):
        return sizeof_fmt(self.size)


@dataclass
class TableInfo:
    files: List[FileInfo]
    number: int = 0


def list_bucket_files(
        bucket_url: str,
        file_pattern: str = '',
        step: int = 1
) -> Dict[TableNames, TableInfo]:
    search_path = os.path.join(bucket_url, file_pattern)
    logger.info(f'Step {step} | List files in {search_path}')
    files = {e: TableInfo(files=[]) for e in TableNames}
    process = subprocess.run(
        ['gsutil', 'ls', '-l', f'{search_path}'],
        check=True, stdout=subprocess.PIPE, universal_newlines=True)
    lines = list(filter(lambda x: len(x) > 0, process.stdout.split('\n')))
    n_lines = len(lines)
    logger.info(f'Step {step} | Listed {n_lines - 1} files')
    for i, line in enumerate(lines):
        if i+1 < n_lines:
            parts = list(filter(lambda x: len(x) > 0, line.split(' ')))
            file_info = FileInfo(
                size=int(parts[0]),
                created_at=datetime.strptime(parts[1], '%Y-%m-%dT%H:%M:%SZ'),
                path=parts[2],
            )
            files[file_info.table_name].number += 1
            files[file_info.table_name].files.append(file_info)
    for table, info in files.items():
        logger.info(f'Step {step} | Bucket {bucket_url} contains {info.number} {table.value} files')
    return files


def download_call(file_path: str, output: str, unzipped_name: str):
    if not os.path.exists(os.path.join(output, unzipped_name)):
        cp = subprocess.run(('gsutil', 'cp', file_path, output), stdout=subprocess.PIPE)
        gunzip = subprocess.run((f'gunzip', os.path.join(output, unzipped_name)), stdout=subprocess.PIPE)
    else:
        logger.info(f'Skipped download for {file_path}')


def download_table_files(
        bucket_url: str,
        files:  List[FileInfo],
        output: str,
        table: TableNames,
        n_file_per_table: int = -1,
        parallel: int = 2
):
    # download one file at the time
    pool = ThreadPool(processes=parallel)
    # start threads
    for i in range(n_file_per_table):
        pool.apply_async(download_call, args=(files[i].path, output), error_callback=lambda e: logger.error(e))
    pool.close()
    pool.join()
    logger.info(f'Downloaded {n_file_per_table} {table.value} into {output}')


def download_files(
        bucket_url: str,
        output: str,
        bucket_files: Dict[TableNames, TableInfo],
        n_file_per_table: int = -1,
        parallel: int = 1
):
    logger.info(f'Starting downloading {n_file_per_table} file per table using {parallel} threads')
    output_path = get_absolute_path(output)
    create_directory(output_path)
    pool = ThreadPool(processes=5)
    for table, info in bucket_files.items():
        pool.apply_async(download_table_files,
                         args=(bucket_url, info['files'], output, table, n_file_per_table, parallel),
                         error_callback=lambda err: logger.error(err))
    pool.close()
    pool.join()
    logger.info(f'All the files have been downloaded in {output}')


def download_pipeline(
        bucket_url: str,
        output: str,
        n_file_per_table: int = -1,
        parallel: int = 1):
    try:
        bucket_files = list_bucket_files(bucket_url, '')
        download_files(bucket_url, output, bucket_files, n_file_per_table, parallel)
    except Exception as e:
        logger.exception(e)
