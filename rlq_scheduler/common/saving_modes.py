from logging import Logger

from rlq_scheduler.agent.agents.base import BaseAgent
from rlq_scheduler.common.config_helper import RunConfigHelper
from rlq_scheduler.common.object_handler.base_handler import ObjectHandler
from rlq_scheduler.common.validation_reward import save_best_checkpoint


def _final_model_saving(folder: str, agent: BaseAgent, object_handler: ObjectHandler, run_name: str):
    path = folder
    serialized_agent = agent.get_serializable_content()
    object_handler.save(
        obj=serialized_agent,
        filename=f'{run_name}.pth',
        path=path,
        pickle_encoding=True,
        max_retries=5,
        trial=0,
        wait_timeout=60
    )


def _best_checkpoint_saving(
        best_checkpoint_index,
        checkpoint_folder,
        model_folder,
        run_name,
        handler: ObjectHandler,
        logger: Logger):
    save_best_checkpoint(
        best_checkpoint_index=best_checkpoint_index,
        checkpoint_folder=f'{checkpoint_folder}/',
        model_folder=model_folder,
        run_name=run_name,
        handler=handler,
        logger=logger
    )


def save_model_run(config: RunConfigHelper,
                   saving_folder: str,
                   run_name: str,
                   agent: BaseAgent,
                   handler: ObjectHandler,
                   logger: Logger,
                   best_checkpoint_index=None,
                   checkpoint_folder=None):
    if agent.is_save_model_enabled() is True:
        saving_mode = config.saving_mode()
        if saving_mode == 'final-model':
            _final_model_saving(saving_folder, agent, handler, run_name)
            logger.info('Saved final model')
        elif saving_mode == 'best-checkpoint':
            _best_checkpoint_saving(best_checkpoint_index, checkpoint_folder, saving_folder, run_name, handler, logger)
            logger.info('Saved best checkpoint model')
        else:
            raise AttributeError('Saving mode {} is not supported'.format(saving_mode))
    else:
        logger.info('Agent model saving not enabled')

