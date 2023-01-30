from logging import Logger

from rlq_scheduler.common.backends.backend_factory import get_backend_adapter
from rlq_scheduler.common.backends.base_backend import BaseBackend
from rlq_scheduler.common.config_helper import GlobalConfigHelper
from rlq_scheduler.common.stats import RunStats, StatsBackend
from rlq_scheduler.common.utils.logger import get_logger


class RunInspector:

    def __init__(self, config=None, config_path='config/global.yml', multi_env_config: dict = None):
        self.name = 'RunInspector'
        self.config: GlobalConfigHelper = GlobalConfigHelper(config, config_path)
        self.logger: Logger = get_logger(self.config.logger())
        self.multi_env_config = multi_env_config
        self.envs_backend = {}
        self.stats_backend: StatsBackend = StatsBackend(global_config=self.config, logger=self.logger)
        self._init_multi_envs()
        self.logger.info(f'{self.name} initialized')

    def _init_multi_envs(self):
        if self.multi_env_config is not None:
            for env_name, env_config in self.multi_env_config.items():
                backend_config = self.config.backend_config()
                backend_config['connection'] = env_config
                self.envs_backend[env_name] = self._init_backend(backend_config)

    def _init_backend(self, backend_config) -> BaseBackend:
        backend_class = get_backend_adapter(self.config.backend_adapter(), backed_type='base')
        return backend_class(config=backend_config, logger=self.logger)

    def _get_env_current_run_code(self, backend: BaseBackend) -> str:
        return backend.get_keys(f'{self.config.redis_statistics_prefix()}_*')[0].split('_')[1]

    def get_run_stats(self, env_name=None, run_code: str = None) -> RunStats:
        default_backend = self.stats_backend.backend
        if env_name is not None:
            env_backend = self.envs_backend[env_name]
            self.stats_backend.backend = env_backend

        if run_code is None:
            run_code = self._get_env_current_run_code(self.stats_backend.backend)

        run_stats: RunStats = self.stats_backend.load(run_code)
        self.stats_backend.backend = default_backend
        return run_stats

    def get_all_envs_run_stats(self) -> tuple:
        stats = []
        for env_name, _ in self.envs_backend.items():
            stats.append(self.get_run_stats(env_name))
        return tuple(stats)
