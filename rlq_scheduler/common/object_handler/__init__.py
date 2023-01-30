import logging
import os

from rlq_scheduler.common.object_handler.base_handler import ObjectHandler
from rlq_scheduler.common.object_handler.minio_handler import MinioObjectHandler
from rlq_scheduler.common.config_helper import GlobalConfigHelper


def create_object_handler(config: GlobalConfigHelper,
                          logger: logging.Logger = None, base=None) -> ObjectHandler or MinioObjectHandler:
    handler_type = config.object_handler_type()
    if handler_type == 'base':
        base_path = config.object_handler_base_folder() if base is None else base
        return ObjectHandler(logger=logger, base_path=base_path)
    elif handler_type == 'minio':
        default_bucket = config.object_handler_base_bucket() if base is None else base
        endpoint = os.getenv('MINIO_ENDPOINT')
        access_key = os.getenv('MINIO_ACCESSKEY')
        secret_key = os.getenv('MINIO_SECRETKEY')
        secure = bool(os.getenv('MINIO_SECURE'))
        return MinioObjectHandler(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            logger=logger,
            default_bucket=default_bucket
        )
    else:
        raise AttributeError('Object handler requested not valid')
