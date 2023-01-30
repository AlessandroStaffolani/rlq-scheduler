import os
import yaml
import json
import logging
import pickle

from glob import glob

ROOT_DIR = os.path.abspath(os.path.relpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../..')))


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


def save_file(path, filename, content, is_yml=False, is_json=False, is_pickle=False):
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
    is_yml: bool
        if True the file generated will be a yaml file, otherwise a general file is created
    is_json: bool
        if True the file generated will be a json file, otherwise a general file is created
    is_pickle
    """
    create_directory(path)
    filepath = os.path.join(path, filename)
    with open(filepath, 'w') as file:
        if is_yml:
            yaml.dump(content, file)
        elif is_json:
            json.dump(content, file)
        elif is_pickle:
            pickle.dump(content, file, protocol=pickle.DEFAULT_PROTOCOL)
        else:
            file.write(content)


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


def get_absolute_path(path, base=ROOT_DIR):
    if not os.path.isabs(path):
        return os.path.join(base, path)
    else:
        return path


def filepath_check(folder_path, filename):
    if not os.path.exists(folder_path):
        raise AttributeError('folder_path: {} not exists'.format(folder_path))
    filepath = os.path.join(folder_path, filename)
    if not os.path.exists(filepath):
        raise AttributeError('filename: {} not exists in folder_path: {}'.format(filename, folder_path))
    return filepath
