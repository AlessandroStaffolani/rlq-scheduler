import os
from typing import Tuple

import yaml
import json
import logging
import pickle
import tarfile

from glob import glob

ROOT_DIR = os.path.abspath(os.path.relpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))


def get_absolute_path(path, base=ROOT_DIR):
    if not os.path.isabs(path):
        return os.path.join(base, path)
    else:
        return path


def get_data_base_dir():
    return get_absolute_path(os.getenv('DATA_BASE_DIR'), ROOT_DIR)


def filter_out_path(path: str) -> str:
    path_to_filter = os.getenv('FILTER_PATH')
    path = path.replace(path_to_filter, '')
    return path


def create_directory(path):
    """
    Create the directory if not exist
    Parameters
    ----------
    path: str
        directory path
    Returns
    -------
        return the string path generated
    """
    if path != '':
        os.makedirs(path, exist_ok=True)
    return path


def create_directory_from_filepath(filepath):
    """
    Create the directory if not exist from a filepath (that is the path plus the filename)
    Parameters
    ----------
    filepath: str
        file path
    Returns
    -------
    str
        return the path (up to final folder) created
    """
    components = filepath.split('/')
    path = '/'.join(components[0: -1])
    create_directory(path)
    return path


def save_file(path: str, filename: str, content, sort_keys=True, **kwargs):
    """
    Save a file to the filesystem
    Parameters
    ----------
    path: str
        path in which save the file (should not contain the filename)
    filename: str
        filename to use for saving the file
    content: str | dict
        string or dictionary to be saved, if dictionary is provided `is_yml` should be True
    sort_keys: bool
    """
    create_directory(path)
    filepath = os.path.join(path, filename)
    if filename.endswith('.yaml') or filename.endswith('.yml'):
        with open(filepath, 'w') as file:
            yaml.safe_dump(content, file, sort_keys=sort_keys, **kwargs)
    elif filename.endswith('.json'):
        with open(filepath, 'w') as file:
            json.dump(content, file, sort_keys=sort_keys, **kwargs)
    elif filename.endswith('.pth') or filename.endswith('.pt'):
        with open(filepath, 'wb') as file:
            pickle.dump(content, file, protocol=pickle.DEFAULT_PROTOCOL, **kwargs)
    else:
        with open(filepath, 'wb') as file:
            file.write(content.encode('utf-8'))


def load_file(file_path, is_yml=False, is_json=False, base_path=ROOT_DIR) -> dict or str:
    full_path = get_absolute_path(file_path, base_path)
    if os.path.exists(full_path):
        with open(full_path, 'r') as file:
            if is_yml:
                return yaml.safe_load(file.read())
            elif is_json:
                return json.load(file)
            else:
                return file.read()
    else:
        raise AttributeError(f'File_path: {full_path} not exists')


def remove_last_n_lines_from_file(filepath, lines_to_remove):
    """
    remove last `lines_to_remove` lines from the file in the `filepath`
    Parameters
    ----------
    filepath
    lines_to_remove
    """
    if os.path.exists(filepath):
        with open(filepath) as file:
            lines = file.readlines()

        if len(lines) > lines_to_remove:
            with open(filepath, 'w') as file:
                file.writelines(lines[:-lines_to_remove])
    else:
        logging.warning('trying to remove {} lines from {}, but file does not exists'
                        .format(str(lines_to_remove), filepath))


def remove_files_from_folder(folder, glob_match):
    files = glob(folder + glob_match)
    for file in files:
        os.remove(file)


def filepath_check(folder_path, filename):
    if not os.path.exists(folder_path):
        raise AttributeError('folder_path: {} not exists'.format(folder_path))
    filepath = os.path.join(folder_path, filename)
    if not os.path.exists(filepath):
        raise AttributeError('filename: {} not exists in folder_path: {}'.format(filename, folder_path))
    return filepath


def compress_folder(
        source_path: str, output_path: str, tar_filename: str, mode='w:gz', recursive=True, base_folder=None) -> str:
    initial_dir = os.getcwd()
    if base_folder is not None:
        os.chdir(base_folder)
    if os.path.exists(source_path):
        output_path = get_absolute_path(output_path)
        create_directory(output_path)
        tar_full_path = os.path.join(output_path, tar_filename)
        with tarfile.open(tar_full_path, mode=mode) as archive:
            archive.add(source_path, recursive=recursive)
        os.chdir(initial_dir)
        return tar_full_path
    else:
        raise AttributeError(f'Source_path does not exists at "{source_path}"')


def extract_file(source_path: str, output_path: str):
    if os.path.exists(source_path):
        with tarfile.open(source_path, "r:gz") as archive:
            archive.extractall(output_path)
    else:
        raise AttributeError(f'Source_path does not exists at "{source_path}"')


def get_filename_from_path(path: str) -> Tuple[str, str]:
    parts = path.split('/')
    root_folder = ''
    if len(path) > 0 and path[0] == '/':
        root_folder = '/'
    return os.path.join(root_folder, *parts[0: -1]), parts[-1]


def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def get_file_len(file_path: str) -> int:
    return sum(1 for line in open(file_path))
