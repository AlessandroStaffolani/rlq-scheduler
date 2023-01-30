import logging
import os
import json
import yaml
import pickle

from rlq_scheduler.common.utils.encoders import object_to_binary, binary_to_object
from rlq_scheduler.common.utils.filesystem import ROOT_DIR, save_file
from rlq_scheduler.common.utils.logger import get_logger


LOGGER_CONFIG = {
    'name': '',
    'level': 20,
    'handlers': [
        {'type': 'console', 'parameters': None}
    ]
}


class ObjectHandler:

    def __init__(self, logger: logging.Logger = None, base_path=ROOT_DIR):
        self.logger = logger if logger is not None else get_logger(LOGGER_CONFIG)
        self.base_path = base_path

    def save(self, obj, filename, path, pickle_encoding=False, **kwargs):
        try:
            base_path = kwargs['base_path'] if 'base_path' in kwargs else None
            is_path_full = kwargs['is_path_full'] if 'is_path_full' in kwargs else False
            if is_path_full is True:
                save_path = path
            else:
                if base_path is None:
                    save_path = os.path.join(self.base_path, path)
                else:
                    save_path = os.path.join(base_path, path)
            extension = filename.split('.')[-1]
            if extension == 'json':
                save_file(path=save_path, filename=filename, content=obj, is_json=True)
            elif extension == 'yaml' or extension == 'yml':
                save_file(path=save_path, filename=filename, content=obj, is_yml=True)
            elif extension == 'pt' or extension == 'pth':
                save_file(path=save_path, filename=filename, content=obj, is_pickle=True)
            else:
                obj_binary = object_to_binary(obj)
                save_file(path=save_path, filename=filename, content=obj_binary.decode('utf-8'))
            return True
        except Exception as e:
            self.logger.exception(e)
            raise e

    def load(self, file_path, pickle_encoding=False, **kwargs):
        try:
            if os.path.exists(file_path):
                extension = file_path.split('.')[-1]
                with open(file_path, 'r') as f:
                    if extension == 'json':
                        obj = json.load(f)
                    elif extension == 'yaml' or extension == 'yml':
                        obj = yaml.safe_load(f.read())
                    elif extension == 'pt' or extension == 'pth':
                        obj = pickle.load(f)
                    else:
                        obj_bites = f.read()
                        obj = binary_to_object(obj_bites.encode('utf-8'))
                return obj
            else:
                raise AttributeError('file_path provided not exists in the host. file_path: "{}"'.format(file_path))
        except Exception as e:
            self.logger.exception(e)
            raise e

    def load_by_run_code(self, file_path, run_code, **kwargs):
        pass

    def list_objects_name(self, path=None, recursive=True, **kwargs):
        pass

    def exists(self, file_path, **kwargs):
        return os.path.exists(file_path)

    def delete(self, file_path, **kwargs):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                self.logger.debug('File: "{}" removed'.format(file_path), resource='BaseObjectHandler')
                return True
        except Exception as e:
            self.logger.exception(e)
            raise e
