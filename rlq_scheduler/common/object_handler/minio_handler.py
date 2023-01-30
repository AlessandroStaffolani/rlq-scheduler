import functools
import io
import os
import time
from logging import Logger

from minio import Minio
from minio.error import MinioException
from urllib3.exceptions import MaxRetryError

from rlq_scheduler.common.object_handler import ObjectHandler
from rlq_scheduler.common.utils.encoders import object_to_binary, binary_to_object


class MinioUnreachableException(Exception):

    def __init__(self, message, *args):
        super(MinioUnreachableException, self).__init__(message, *args)


def handle_minio_call(func):
    @functools.wraps(func)
    def wrapper_function(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except MaxRetryError:
            message = 'Minio unreachable at {}'.format(self.endpoint)
            self.logger.error(message)
            raise MinioUnreachableException(message)
        except MinioException:
            message = 'Minio failed to perform the requested operation using the provided access key and secret key'
            self.logger.error(message)
            raise MinioUnreachableException(message)
        except Exception as e:
            self.logger.exception(e)
            raise e

    return wrapper_function


class MinioObjectHandler(ObjectHandler):

    def __init__(self,
                 endpoint: str,
                 access_key: str,
                 secret_key: str,
                 secure: bool,
                 logger: Logger = None,
                 default_bucket: str = 'data'):
        super(MinioObjectHandler, self).__init__(logger=logger)
        self.default_bucket = default_bucket
        self.endpoint = endpoint
        self.client: Minio = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        self._create_bucket(bucket=self.default_bucket)

    @handle_minio_call
    def save(self, obj, filename, path, pickle_encoding=False, **kwargs):
        content_type = kwargs['content_type'] if 'content_type' in kwargs else 'application/octet-stream'
        bucket = self.default_bucket
        max_retries = None
        trial = 0
        wait_timeout = 0
        if 'bucket' in kwargs:
            bucket = kwargs['bucket']
            self._create_bucket(bucket=bucket)
        if 'max_retries' in kwargs:
            max_retries = kwargs['max_retries']
        if 'trial' in kwargs:
            trial = kwargs['trial']
        if 'wait_timeout' in kwargs:
            wait_timeout = kwargs['wait_timeout']
        object_name = filename
        if path is not None and len(path) > 0:
            object_name = f'{path}/{filename}'
        obj_bytes = object_to_binary(obj, pickle_encoding=pickle_encoding)
        obj_stream = io.BytesIO(obj_bytes)
        try:
            result = self.client.put_object(
                bucket_name=bucket,
                object_name=object_name,
                data=obj_stream,
                length=len(obj_bytes),
                content_type=content_type)
            self.logger.debug('Uploaded to minio object {} with result: {}'.format(filename, result))
            return True
        except Exception as e:
            if max_retries is not None:
                # check if trial not exceed max_retries if it doesn't retry else raise the exception
                if trial < max_retries:
                    self.logger.warning('Error while uploading file to minio, current trial is {} '
                                        'max_retries is {}, so I\'m going to retry in {} seconds. Object name = {}'
                                        .format(trial, max_retries, wait_timeout, filename, object_name))
                    time.sleep(wait_timeout)
                    return self.save(obj=obj,
                                     filename=filename,
                                     path=path,
                                     pickle_encoding=pickle_encoding,
                                     bucket=bucket,
                                     trial=trial + 1,
                                     max_retries=max_retries,
                                     wait_timeout=wait_timeout)
                else:
                    self.logger.error('Impossible to upload for {} trials. Raising the error'.format(max_retries))
                    raise e
            else:
                raise e

    @handle_minio_call
    def load(self, file_path, pickle_encoding=False, **kwargs):
        bucket = self.default_bucket
        if 'bucket' in kwargs:
            bucket = kwargs['bucket']
        keep_binaries = False
        if 'keep_binaries' in kwargs:
            keep_binaries = kwargs['keep_binaries']
        response = self.client.get_object(
            bucket_name=bucket,
            object_name=file_path
        )
        obj_bytes = response.data

        if not keep_binaries:
            obj = binary_to_object(obj_bytes, pickle_encoding=pickle_encoding)
        else:
            obj = obj_bytes

        response.close()
        response.release_conn()
        return obj

    @handle_minio_call
    def load_by_run_code(self, file_path, run_code, **kwargs):
        bucket = self.default_bucket
        if 'bucket' in kwargs:
            bucket = kwargs['bucket']
        prefix = os.path.join(file_path, run_code)
        results = self.client.list_objects(
            bucket_name=bucket,
            prefix=prefix,
            recursive=True
        )
        object_loaded = None
        for obj in results:
            pickle_encoding = False
            if 'models' in obj.object_name:
                pickle_encoding = True
            object_loaded = self.load(
                file_path=obj.object_name,
                pickle_encoding=pickle_encoding,
                bucket=obj.bucket_name
            )
        return object_loaded

    def list_objects_name(self, path=None, recursive=True, **kwargs):
        bucket = self.default_bucket
        if 'bucket' in kwargs:
            bucket = kwargs['bucket']
        results = self.client.list_objects(bucket, prefix=path, recursive=recursive)
        names = []
        for obj in results:
            names.append(obj.object_name)
        return names

    @handle_minio_call
    def delete(self, file_path, **kwargs):
        bucket = self.default_bucket
        if 'bucket' in kwargs:
            bucket = kwargs['bucket']
        self.client.remove_object(
            bucket_name=bucket,
            object_name=file_path
        )
        return True

    @handle_minio_call
    def exists(self, file_path, bucket_name=None):
        bucket = bucket_name if bucket_name is not None else self.default_bucket
        try:
            _ = self.client.stat_object(bucket_name=bucket, object_name=file_path)
            return True
        except MinioException:
            return False

    @handle_minio_call
    def _create_bucket(self, bucket):
        if self.client.bucket_exists(bucket_name=bucket) is False:
            self.client.make_bucket(bucket_name=bucket)
