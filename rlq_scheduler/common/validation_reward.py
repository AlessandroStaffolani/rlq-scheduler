import json
import time
from enum import Enum
from logging import Logger

import numpy as np

from rlq_scheduler.common.backends.base_backend import BaseBackend
from rlq_scheduler.common.config_helper import GlobalConfigHelper, RunConfigHelper
from rlq_scheduler.common.object_handler.base_handler import ObjectHandler
from rlq_scheduler.common.stats import StatsBackend


class ValidationStructItem(str, Enum):
    TIME_STEP = 'time_step'
    CREATED_AT = 'created_at'
    REWARD = 'reward'
    UPDATED_AT = 'updated_at'


def empty_validation_struct() -> dict:
    return {
        ValidationStructItem.TIME_STEP: None,
        ValidationStructItem.CREATED_AT: time.time(),
        ValidationStructItem.REWARD: None,
        ValidationStructItem.UPDATED_AT: None,
    }


def parse_validation_json_struct(json_string: str):
    json_struct: dict = json.loads(json_string)
    struct = {}
    for key, value in json_struct.items():
        struct[ValidationStructItem(key)] = value
    return struct


def get_average_validation_reward_for_interval(
        global_config: GlobalConfigHelper,
        run_config: RunConfigHelper,
        backend: BaseBackend,
        stats_backend: StatsBackend,
        current_run: str,
        logger: Logger):
    validation_entries = backend.get_all(f'{global_config.backend_validation_reward_prefix()}_*')
    validation_entries = [parse_validation_json_struct(entry) for entry in validation_entries]
    validation_entries.sort(key=lambda x: x[ValidationStructItem.TIME_STEP])
    checkpoint_frequency = run_config.checkpoint_frequency()
    data = []
    current = np.zeros(checkpoint_frequency, dtype=np.float)
    max_mean = 0
    max_checkpoint = 0
    i = 0
    for entry in validation_entries:
        if entry[ValidationStructItem.TIME_STEP] % checkpoint_frequency == 0:
            # new checkpoint
            if entry[ValidationStructItem.REWARD] is not None:
                current[i] = entry[ValidationStructItem.REWARD]
            mean = current.mean()
            if mean > max_mean:
                max_mean = mean
                max_checkpoint = len(data)
            data.append(np.copy(current))
            current = np.zeros(checkpoint_frequency, dtype=np.float)
            i = 0
        else:
            # current checkpoint
            if entry[ValidationStructItem.REWARD] is not None:
                current[i] = entry[ValidationStructItem.REWARD]
            i += 1
    logger.info('Max average reward is {} and best checkpoint is {}'.format(max_mean, max_checkpoint),
                resource='ValidationReward')
    data_to_list = [arr.tolist() for arr in data]
    result = stats_backend.save_stats_group_property(
        stats_run_code=current_run,
        prop='validation_reward',
        value=data_to_list
    )
    if result is True:
        logger.debug('Added validation_reward to stats',
                     resource='ValidationReward')
    else:
        logger.warning('Impossible to save validation_reward to stats',
                       resource='ValidationReward')
    return max_checkpoint, max_mean


def save_best_checkpoint(
        best_checkpoint_index,
        checkpoint_folder,
        model_folder,
        run_name,
        handler: ObjectHandler,
        logger: Logger):
    checkpoints = handler.list_objects_name(path=checkpoint_folder, recursive=False)
    best_name = checkpoints[best_checkpoint_index]
    best_model = handler.load(best_name, pickle_encoding=True)
    logger.debug('Best model = {}'.format(best_model))
    handler.save(
        obj=best_model,
        filename=f'{run_name}.pth',
        path=model_folder,
        pickle_encoding=True,
        max_retries=5,
        trial=0,
        wait_timeout=60
    )

