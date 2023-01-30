import os
from copy import deepcopy
from enum import Enum

import yaml

from rlq_scheduler.common.utils.config_loaders import load_yaml_config
from rlq_scheduler.common.utils.filesystem import ROOT_DIR, get_absolute_path, save_file


class ExecutionTimeMode(Enum):
    EVENT = 'event'
    RESULT = 'result'


class BaseConfigHelper:

    def __init__(self, config: dict = None, config_path: str = None, name='Config'):
        if config is not None:
            self.config = config
            self._config_path = None
        elif config_path is not None:
            self._config_path = get_absolute_path(config_path, base=ROOT_DIR)
            if not os.path.exists(self._config_path):
                raise AttributeError('config_path: {} not exist'.format(self._config_path))
            self.config = load_yaml_config(self._config_path)
        else:
            raise AttributeError('config and config_path are None')
        self.name = name

    def __getitem__(self, item):
        return self.config[item]

    def __len__(self):
        return len(self.config)

    def items(self):
        return self.config.items()

    def keys(self):
        return self.config.keys()

    def values(self):
        return self.config.values()

    def __str__(self):
        return '<{}={}>'.format(self.name, self.config)

    def logger(self):
        if 'logger' in self.config:
            return self['logger']
        else:
            return None

    def logger_level(self):
        if 'logger' in self.config:
            return self['logger']['level']
        else:
            return None

    def logger_name(self):
        if 'logger' in self.config:
            return self['logger']['name']
        else:
            return None

    def logger_handlers(self):
        if 'logger' in self.config:
            return self['logger']['handlers']
        else:
            return None

    def to_config_map(self, name, data_key, component, part_of, instance='config-map'):
        data = {
            data_key: yaml.safe_dump(self.config, sort_keys=False)
        }
        config_map = {
            'apiVersion': 'v1',
            'kind': 'ConfigMap',
            'metadata': {
                'name': name,
                'labels': {
                    'app.kubernetes.io/name': name,
                    'app.kubernetes.io/instance': instance,
                    'app.kubernetes.io/component': component,
                    'app.kubernetes.io/part-of': part_of
                }
            },
            'data': data
        }
        return config_map

    def save_to_file(self, filepath, filename=None):
        name = self.name.lower() if filename is None else filename
        name += '.yml'
        path = get_absolute_path(filepath)
        save_file(path, name, self.config, is_yml=True)


class GlobalConfigHelper(BaseConfigHelper):

    def __init__(self, config=None, config_path='config/global.yml'):
        super(GlobalConfigHelper, self).__init__(config=config, config_path=config_path, name='GlobalConfig')
        self._task_classes_configs: dict = self.config['task_classes']
        self._worker_classes_config: dict = self.config['worker_classes']

    def available_worker_classes(self) -> list:
        return list(self._worker_classes_config.keys())

    def worker_class_cost_per_usage(self, worker_class, internal_cost=True):
        cost_config = self._worker_classes_config[worker_class]['cost_config']

        if internal_cost is True:
            return cost_config['cost_internal']
        else:
            return cost_config['cost_external']

    def worker_class_capacity(self, worker_class):
        return self._worker_classes_config[worker_class]['capacity']

    def worker_class_speed_factor(self, worker_class):
        return self._worker_classes_config[worker_class]['speed_factor']

    def worker_class_replicas(self, worker_class):
        return self._worker_classes_config[worker_class]['replicas']

    def worker_class_resources_limits(self, worker_class):
        return self._worker_classes_config[worker_class]['resources']

    def available_tasks_classes(self) -> list:
        return list(self._task_classes_configs.keys())

    def task_class(self, task_class):
        return self._task_classes_configs[task_class]

    def task_class_config(self, task_class):
        return self._task_classes_configs[task_class]['parameters_range']

    def task_class_func_name(self, task_class):
        task_class = self.task_class(task_class)
        return task_class['func_name']

    def task_class_waiting_cost(self, task_class) -> float:
        return float(self._task_classes_configs[task_class]['waiting_cost'])

    def task_class_constraints(self, task_class):
        return self._task_classes_configs[task_class]['constraints']

    def task_class_wait_constraint(self, task_class):
        return self._task_classes_configs[task_class]['constraints']['wait']

    def task_class_wait_constraint_max(self, task_class):
        return self._task_classes_configs[task_class]['constraints']['wait']['max']

    def task_class_wait_constraint_penalty(self, task_class):
        return self._task_classes_configs[task_class]['constraints']['wait']['penalty']

    def task_class_execution_constraint(self, task_class):
        return self._task_classes_configs[task_class]['constraints']['execution']

    def task_class_execution_constraint_max(self, task_class):
        return self._task_classes_configs[task_class]['constraints']['execution']['max']

    def task_class_execution_constraint_penalty(self, task_class):
        return self._task_classes_configs[task_class]['constraints']['execution']['penalty']

    def task_class_capacity_usage(self, task_class):
        return self._task_classes_configs[task_class]['capacity_usage']

    def task_class_capacity_usage_cost(self, task_class):
        return self.task_class_capacity_usage(task_class)['cost']

    def task_class_capacity_usage_parameters_range(self, task_class):
        task_ranges = self.task_class_config(task_class)
        if 'd' in task_ranges:
            n_min = task_ranges['n']['min']
            d_min = task_ranges['d']['min']
            min_value = n_min * d_min
            n_max = task_ranges['n']['max'] - 1
            d_max = task_ranges['d']['max'] - 1
            max_value = n_max * d_max
            return min_value, max_value
        else:
            return task_ranges['n']['min'], task_ranges['n']['max'] - 1

    def task_class_capacity_usage_delta_range(self, task_class):
        ranges = self.task_class_capacity_usage(task_class)
        return ranges['cost_delta_min'], ranges['cost_delta_max']

    def count_available_tasks_classes(self) -> int:
        return len(self.available_tasks_classes())

    def count_available_worker_classes(self) -> int:
        return len(self.available_worker_classes())

    def task_class_index(self, task_class) -> int:
        return self.available_tasks_classes().index(task_class)

    def state_size(self):
        size = self.count_available_tasks_classes() + self.count_available_worker_classes()
        return size

    def context_size(self, is_expandable_pool_enabled=False):
        size = self.count_available_tasks_classes() + self.count_available_worker_classes()
        if is_expandable_pool_enabled:
            size *= 2
        return size

    def task_classes(self):
        return self._task_classes_configs

    def worker_classes(self):
        return self._worker_classes_config

    def api(self):
        return self['api']

    def api_endpoints(self):
        return self['api']['endpoints']

    def agent_api(self):
        return self['api']['endpoints']['agent']

    def trajectory_collector_api(self):
        return self['api']['endpoints']['trajectory_collector']

    def system_manager_api(self):
        return self['api']['endpoints']['system_manager']

    def api_resource_endpoint(self, component):
        return self['api']['endpoints'][component]

    def state_builder(self):
        return self['state_builder']

    def state_builder_mode(self):
        return self.state_builder()['mode']

    def state_builder_state_key(self):
        return self.state_builder()['state_key']

    def state_builder_resource_usage_key(self):
        return self.state_builder()['resource_usage_key']

    def state_builder_task_frequency_key(self):
        return self.state_builder()['task_frequency_key']

    def state_builder_worker_state_key(self):
        return self.state_builder()['worker_state_key']

    def state_builder_pool_load_key(self):
        return self.state_builder()['pool_load_key']

    def state_builder_pool_utilization_key(self):
        return self.state_builder()['pool_utilization_key']

    def backend(self):
        return self['backend']

    def backend_adapter(self):
        return self['backend']['adapter']

    def backend_config(self):
        return self['backend']['config']

    def backend_connection_config(self):
        return self['backend']['config']['connection']

    def backend_trajectory_prefix(self):
        return self['backend']['config']['trajectory_prefix']

    def backend_previous_trajectory_key(self):
        return self['backend']['config']['previous_trajectory_key']

    def backend_task_waiting_time_prefix(self):
        return self['backend']['config']['task_waiting_time_prefix']

    def backend_validation_reward_prefix(self):
        return self['backend']['config']['validation_reward_prefix']

    def backend_assignment_entry_prefix(self):
        prefix = self['backend']['config']['assignment_entry_prefix']
        if prefix is None:
            return 'assignment_entry'
        else:
            return prefix

    def object_handler(self):
        return self['object_handler']

    def object_handler_type(self):
        return self['object_handler']['type']

    def object_handler_base_folder(self):
        return self['object_handler']['base_folder']

    def object_handler_base_bucket(self):
        return self['object_handler']['default_bucket']

    def run_name_prefix(self):
        return self['run_name_prefix']

    def tensorboard(self):
        return self['tensorboard']

    def is_tensorboard_enabled(self):
        return bool(self['tensorboard']['enabled'])

    def tensorboard_transport(self):
        return self['tensorboard']['transport']

    def tensorboard_log_dir_base(self):
        return self['tensorboard']['log_dir_base']

    def redis(self):
        return self['redis']

    def redis_config(self):
        return self['redis']['config']

    def redis_statistics_prefix(self):
        return self['redis']['statistics_prefix']

    def redis_system_info_topic(self):
        return self['redis']['system_info_topic']

    def task_broker(self):
        return self['task_broker']

    def task_broker_task_name(self):
        return self['task_broker']['task_name']

    def task_broker_worker_name(self):
        return self['task_broker']['worker_name']

    def task_broker_queue_name(self):
        return self['task_broker']['queue_name']

    def datasets(self):
        return self['datasets']

    def datasets_google_traces(self):
        return self.datasets()['google_traces']

    def datasets_google_traces_eval_dataset_path(self):
        return self.datasets_google_traces()['eval_dataset_path']

    def datasets_google_traces_synthetic_dataset_path(self):
        return self.datasets_google_traces()['synthetic_dataset_path']

    def datasets_google_traces_task_function_name(self):
        return self.datasets_google_traces()['task_function_name']

    def saver(self):
        return self['saver']

    def saver_save_interval(self):
        return self.saver()['save_interval']

    @staticmethod
    def get_worker_class_from_fullname(fullname):
        parts = fullname.split('@')
        return parts[0]

    @staticmethod
    def task_class_from_celery_task_name(celery_task_name):
        parts = celery_task_name.split('.')
        return parts[-1]


class AgentConfigHelper(BaseConfigHelper):

    def __init__(self, config=None, config_path='config/agent.yml'):
        super(AgentConfigHelper, self).__init__(config=config, config_path=config_path, name='AgentConfig')


class TaskGeneratorConfigHelper(BaseConfigHelper):

    def __init__(self, config=None, config_path='config/task_generator.yml'):
        super(TaskGeneratorConfigHelper, self).__init__(config=config,
                                                        config_path=config_path,
                                                        name='TaskGeneratorConfig')

    def task_generator(self):
        return self['task_generator']

    def task_generator_is_local(self):
        return self['task_generator']['is_local']

    def task_generator_use_kube(self):
        return self['task_generator']['use_kube']

    def random_seed(self):
        return self['task_generator']['random_seed']


class TrajectoryCollectorConfigHelper(BaseConfigHelper):

    def __init__(self, config=None, config_path='config/trajectory_collector.yml'):
        super(TrajectoryCollectorConfigHelper, self).__init__(
            config=config,
            config_path=config_path,
            name='TrajectoryCollectorConfig')

    def trajectory_builder(self):
        return self['trajectory_builder']

    def trajectory_builder_instances(self):
        return self['trajectory_builder']['instances']

    def consumer(self):
        return self['consumer']

    def consumer_queue(self):
        return self['consumer']['queue']

    def consumer_queue_type(self):
        return self['consumer']['queue']['type']

    def consumer_queue_state_creation_key(self):
        return self['consumer']['queue']['state_creation_key']

    def consumer_queue_compute_reward_key(self):
        return self['consumer']['queue']['compute_reward_key']

    def consumer_queue_config(self):
        return self['consumer']['queue']['config']

    def consumer_queue_config_connection(self):
        return self['consumer']['queue']['config']['connection']

    def worker_state(self):
        return self['worker_state']

    def is_worker_state_enabled(self):
        return self['worker_state']['enabled']

    def worker_state_update_interval(self):
        return self['worker_state']['update_interval']

    def worker_state_workers_ping_interval(self):
        return self['worker_state']['workers_ping_interval']


class DeployerManagerConfigHelper(BaseConfigHelper):

    def __init__(self, config=None, config_path=None):
        super(DeployerManagerConfigHelper, self).__init__(
            config=config,
            config_path=config_path,
            name='DeployerManager')

    def deployer_manager(self):
        return self['deployer_manager']

    def deployer_manager_pool_size(self):
        return self['deployer_manager']['pool_size']

    def kube(self):
        return self['kube']

    def kube_config_file(self):
        return self['kube']['config_file']

    def kube_config_mode(self):
        mode = self['kube']['config_mode']
        if mode != 'in':
            return 'out'
        else:
            return mode

    def kube_namespace(self):
        return self['kube']['namespace']

    def kube_common_labels(self):
        return self['kube']['common_labels']

    def kube_image_version(self):
        return self['kube']['image_version']

    def custom_images(self):
        return self['custom_images']

    def config_maps_to_load(self):
        return self['config_maps_to_load']

    def config_maps_to_create(self):
        return self['config_maps_to_create']

    def deployments(self):
        return self['deployments']

    def deployments_number(self):
        return len(list(self.deployments().keys())) - 1

    def redis_queue_deployment(self):
        return self['deployments']['redis-queue']

    def redis_queue_deployment_file(self):
        return self['deployments']['redis-queue']['file']

    def redis_shared_memory_deployment(self):
        return self['deployments']['redis-shared-memory']

    def redis_shared_memory_deployment_file(self):
        return self['deployments']['redis-shared-memory']['file']

    def health_tool_deployment(self):
        return self['deployments']['system_manager']

    def system_manager_deployment_file(self):
        return self['deployments']['system_manager']['file']

    def offline_trainer_deployment_file(self):
        return self['deployments']['offline_trainer']['file']

    def task_broker_deployment(self):
        return self['deployments']['task_broker']

    def task_broker_deployment_file(self):
        return self['deployments']['task_broker']['file']

    def worker_class_template_deployment(self):
        return self['deployments']['worker_class_template']

    def worker_class_template_deployment_file(self):
        return self['deployments']['worker_class_template']['file']

    def flower_deployment(self):
        return self['deployments']['flower']

    def flower_deployment_file(self):
        return self['deployments']['flower']['file']

    def trajectory_collector_deployment(self):
        return self['deployments']['trajectory_collector']

    def trajectory_collector_deployment_file(self):
        return self['deployments']['trajectory_collector']['file']

    def agent_deployment(self):
        return self['deployments']['agent']

    def agent_deployment_file(self):
        return self['deployments']['agent']['file']

    def task_generator_deployment(self):
        return self['deployments']['task_generator']

    def task_generator_deployment_file(self):
        return self['deployments']['task_generator']['file']

    def docker_registry_secret_file(self):
        return self['secrets']['docker_registry']

    def minio_secret_file(self):
        return self['secrets']['minio']

    def mongo_secret_file(self):
        return self['secrets']['mongo']

    def elasticsearch_secret_file(self):
        return self['secrets']['elasticsearch']


class SystemManagerConfigHelper(BaseConfigHelper):

    def __init__(self, config=None, config_path='config/system_manager.yml'):
        super(SystemManagerConfigHelper, self).__init__(config=config,
                                                        config_path=config_path,
                                                        name='SystemManagerConfig')

    def system_resources(self):
        return self['system_resources']

    def run_manager(self):
        return self['run_manager']

    def is_auto_start(self):
        return self['run_manager']['auto_start']

    def is_auto_run(self):
        return self['run_manager']['auto_run']

    def start_from(self):
        return self['run_manager']['start_from']

    def config_folder(self):
        return self['config_folder']

    def stats(self):
        return self['stats']

    def stats_folder_path(self):
        return self['stats']['folder_path']


class RunConfigHelper(BaseConfigHelper):

    def __init__(self, config=None, config_path='config/run_config.yml',
                 global_config=None, global_config_path='config/global.yml'):
        super(RunConfigHelper, self).__init__(config=config,
                                              config_path=config_path,
                                              name='RunConfigHelper')
        self._global_config = GlobalConfigHelper(config=global_config, config_path=global_config_path)
        self._task_classes_configs: dict = self['task_classes']
        self._worker_classes_config: dict = self['worker_classes']

    def global_config(self):
        return self['global']

    def features_enabled(self):
        return self['global']['features_enabled']

    def is_waiting_time_enabled(self):
        return self['global']['features_enabled']['waiting_time']

    def execution_time_mode(self):
        return ExecutionTimeMode(self['global']['features_enabled']['execution_time'])

    def is_context_enabled(self):
        return self['global']['features_enabled']['context']

    def is_bootstrapping_enabled(self):
        return self['global']['features_enabled']['bootstrapping']

    def is_trajectory_saving_enabled(self):
        return self['global']['features_enabled']['trajectory_saving']

    def is_evaluation_enabled(self):
        return self['global']['features_enabled']['evaluation']

    def is_google_traces_mode_enabled(self):
        return self['global']['features_enabled']['google_traces_mode']

    def google_traces_time_multiplier(self):
        return self['global']['features_enabled']['google_traces_time_multiplier']

    def is_replicas_normalization(self):
        return self['global']['features_enabled']['replicas_normalization']

    def save_properties(self):
        return self.global_config()['save_properties']

    def run_name_prefix(self):
        return self.save_properties()['run_name_prefix']

    def checkpoint_frequency(self):
        return self.save_properties()['checkpoint_frequency']

    def saving_mode(self):
        return self.save_properties()['saving_mode']

    def penalties(self):
        return self.global_config()['penalties']

    def out_of_budget_penalty(self):
        return self.penalties()['out_of_budget']

    def task_failed_penalty(self):
        return self.penalties()['task_failed']

    def functions(self):
        return self['global']['functions']

    def execution_cost_function(self):
        return self['global']['functions']['execution_cost']

    def execution_cost_function_type(self):
        return self['global']['functions']['execution_cost']['type']

    def execution_cost_function_train_data(self):
        return self['global']['functions']['execution_cost']['train_data']

    def reward_function(self):
        return self['global']['functions']['reward_function']

    def reward_function_type(self):
        return self['global']['functions']['reward_function']['type']

    def reward_function_extra_parameters(self):
        return self['global']['functions']['reward_function']['extra_parameters']

    def agent_type(self):
        return self['global']['features_enabled']['agent_type']

    def agent_type_name(self):
        return self['global']['features_enabled']['agent_type']['name']

    def is_expandable_pool_enabled(self):
        return self['global']['features_enabled']['expandable_pool']

    def state(self):
        return self['global']['state']

    def state_features(self):
        return self['global']['state']['features']

    def state_time_window(self):
        return self['global']['state']['time_window']

    def context_features(self):
        return self['global']['context']['features']

    def task_generator_config(self):
        return self['task_generator']

    def task_generator_random_seed(self):
        return self['task_generator']['random_seed']

    def task_bootstrapping(self):
        return self.task_generator_config()['bootstrapping']

    def tasks_bootstrapping_to_skip(self):
        return self.task_bootstrapping()['skip']

    def tasks_bootstrapping_generation_distribution(self):
        return self.task_bootstrapping()['distribution']

    def tasks_bootstrapping_tasks_to_generate(self):
        return self.task_bootstrapping()['tasks_to_generate']

    def tasks_bootstrapping_rate_interval(self):
        return self.task_bootstrapping()['rate_per_interval']

    def tasks_bootstrapping_rate_interval_range(self):
        return self.task_bootstrapping()['rate_per_interval_range']

    def tasks_to_generate(self):
        return self['task_generator']['tasks_to_generate']

    def tasks_to_generate_round(self, gen_round):
        return self['task_generator']['tasks_to_generate'][gen_round]

    def tasks_to_generate_number_round(self, gen_round):
        return self['task_generator']['tasks_to_generate'][gen_round]['tasks_to_generate']

    def tasks_to_skip(self, gen_round):
        return self['task_generator']['tasks_to_generate'][gen_round]['skip']

    def tasks_generation_distribution(self, gen_round):
        return self['task_generator']['tasks_to_generate'][gen_round]['distribution']

    def tasks_rate_per_minute(self, gen_round):
        return self['task_generator']['tasks_to_generate'][gen_round]['rate_per_interval']

    def tasks_to_generate_round_rate(self, gen_round):
        if self.tasks_generation_distribution(gen_round) == 'poisson_fixed':
            return self.tasks_rate_per_minute(gen_round)
        elif self.tasks_generation_distribution(gen_round) == 'poisson_variable':
            return self.tasks_rate_per_interval_range(gen_round)
        else:
            return self.tasks_to_generate_number_round(gen_round)

    def tasks_rate_per_interval_range(self, gen_round):
        if 'rate_per_interval_range' in self['task_generator']['tasks_to_generate'][gen_round]:
            return self['task_generator']['tasks_to_generate'][gen_round]['rate_per_interval_range']
        else:
            return [self.tasks_rate_per_minute(gen_round), self.tasks_rate_per_minute(gen_round) + 1]

    def tasks_to_generate_total_number(self):
        tasks_to_generate = 0
        for task_gen_config in self.tasks_to_generate():
            tasks_to_generate += task_gen_config['tasks_to_generate']
        return tasks_to_generate

    def tasks_to_skip_total(self):
        skip = 0
        for i in range(len(self.tasks_to_generate())):
            skip += self.tasks_to_skip(i)
        return skip

    def agent(self):
        return self['agent']

    def agent_global(self):
        return self['agent']['global']

    def agents_parameters(self, agent=None):
        if agent is None:
            return self['agent']['agents_parameters']
        else:
            return self['agent']['agents_parameters'][agent]

    def policies_parameters(self, policy=None):
        if policy is None:
            return self['agent']['policies_parameters']
        else:
            return self['agent']['policies_parameters'][policy]

    def agent_action_space(self):
        return self['agent']['global']['action_space']

    def agent_load_config(self):
        return self['agent']['global']['load_model_config']

    def agent_reward_multiplier(self):
        return self['agent']['global']['reward_multiplier']

    def agent_save_model_config(self):
        return self['agent']['global']['save_model_config']

    def is_agent_in_training_mode(self):
        return self['agent']['global']['train']

    def agent_full_name(self):
        agent_name = self.agent_type_name()
        agent_policy = self.agent_type_policy()
        agent_name_parts = []
        for part in agent_name.split('-'):
            if part == 'dqn' or part == 'ucb':
                agent_name_parts.append(part.upper())
            else:
                agent_name_parts.append(part.capitalize())
        name = ''.join(agent_name_parts)
        if agent_policy is not None:
            policy_parts = []
            for part in agent_policy.split('-'):
                if part == 'ucb':
                    policy_parts.append(part.upper())
                elif part == 'e':
                    policy_parts.append('Epsilon')
                else:
                    policy_parts.append(part.capitalize())
            policy = ''.join(policy_parts)
            name += f'_{policy}'
        return name

    def agent_config(self, agent_type=None):
        if agent_type is None:
            agent_type = {'name': 'random'}
        global_conf = self.agent_global()
        agent_name = agent_type['name']
        agent_parameters = self.agents_parameters(agent_name)
        agent_config = deepcopy(global_conf)
        agent_config['type'] = agent_name
        if agent_parameters is not None:
            for key, val in agent_parameters.items():
                agent_config[key] = val
        return agent_config

    def task_classes(self):
        tasks = self._task_classes_configs
        if tasks is None:
            return self._global_config.task_classes()
        return tasks

    def worker_classes(self):
        workers = self._worker_classes_config
        if workers is None:
            return self._global_config.worker_classes()
        return workers

    def available_worker_classes(self) -> list:
        return list(self.worker_classes().keys())

    def available_tasks_classes(self) -> list:
        return list(self.task_classes().keys())

    def worker_class_cost_per_usage(self, worker_class, internal_cost=True):
        cost_config = self.worker_classes()[worker_class]['cost_config']

        if internal_cost is True:
            return cost_config['cost_internal']
        else:
            return cost_config['cost_external']

    def worker_class_capacity(self, worker_class):
        return self._worker_classes_config[worker_class]['capacity']

    def worker_class_speed_factor(self, worker_class):
        return self._worker_classes_config[worker_class]['speed_factor']

    def task_class(self, task_class):
        return self.task_classes()[task_class]

    def task_class_config(self, task_class):
        return self.task_classes()[task_class]['parameters_range']

    def task_class_func_name(self, task_class):
        task_class = self.task_class(task_class)
        return task_class['func_name']

    def task_class_waiting_cost(self, task_class) -> float:
        return float(self.task_classes()[task_class]['waiting_cost'])

    def task_class_constraints(self, task_class):
        return self._task_classes_configs[task_class]['constraints']

    def task_class_wait_constraint(self, task_class):
        return self._task_classes_configs[task_class]['constraints']['wait']

    def task_class_wait_constraint_max(self, task_class):
        return self._task_classes_configs[task_class]['constraints']['wait']['max']

    def task_class_wait_constraint_penalty(self, task_class):
        return self._task_classes_configs[task_class]['constraints']['wait']['penalty']

    def task_class_execution_constraint(self, task_class):
        return self._task_classes_configs[task_class]['constraints']['execution']

    def task_class_execution_constraint_max(self, task_class):
        return self._task_classes_configs[task_class]['constraints']['execution']['max']

    def task_class_execution_constraint_penalty(self, task_class):
        return self._task_classes_configs[task_class]['constraints']['execution']['penalty']

    def task_class_capacity_usage(self, task_class):
        return self._task_classes_configs[task_class]['capacity_usage']

    def task_class_capacity_usage_cost(self, task_class):
        return self.task_class_capacity_usage(task_class)['cost']

    def task_class_capacity_usage_parameters_range(self, task_class):
        task_ranges = self.task_class_config(task_class)
        if 'd' in task_ranges:
            n_min = task_ranges['n']['min']
            d_min = task_ranges['d']['min']
            min_value = n_min * d_min
            n_max = task_ranges['n']['max'] - 1
            d_max = task_ranges['d']['max'] - 1
            max_value = n_max * d_max
            return min_value, max_value
        else:
            return task_ranges['n']['min'], task_ranges['n']['max'] - 1

    def task_class_capacity_usage_delta_range(self, task_class):
        ranges = self.task_class_capacity_usage(task_class)
        return ranges['cost_delta_min'], ranges['cost_delta_max']

    def count_available_tasks_classes(self) -> int:
        return len(self.available_tasks_classes())

    def count_available_worker_classes(self) -> int:
        return len(self.available_worker_classes())

    def task_class_index(self, task_class) -> int:
        return self.available_tasks_classes().index(task_class)

    def state_size(self):
        size = 0
        values_types = {
            'task_classes': self.count_available_tasks_classes(),
            'worker_classes': self.count_available_worker_classes()
        }
        for feature_name, feature_conf in self.state_features().items():
            if isinstance(feature_conf['values'], str):
                values = values_types[feature_conf['values']]
                if feature_name == 'action' and self.is_expandable_pool_enabled():
                    values *= 2
                size += values
            else:
                size += feature_conf['values']
        # size = self.count_available_tasks_classes() + self.count_available_worker_classes()
        return size

    def context_size(self):
        size = 0
        values_types = {
            'task_classes': self.count_available_tasks_classes(),
            'worker_classes': self.count_available_worker_classes()
        }
        for feature_name, feature_conf in self.context_features().items():
            if isinstance(feature_conf['values'], str):
                values = values_types[feature_conf['values']]
                if feature_name == 'action' and self.is_expandable_pool_enabled():
                    values *= 2
                size += values
            else:
                size += feature_conf['values']
        # size = self.count_available_tasks_classes() + self.count_available_worker_classes()
        return size


class MultiRunConfigHelper(BaseConfigHelper):

    def __init__(self, config=None, config_path='config/multi_run_config.yml'):
        super(MultiRunConfigHelper, self).__init__(config=config,
                                                   config_path=config_path,
                                                   name='MultiRunConfigHelper')

    def global_config(self):
        return self['global']

    def global_seed(self):
        return self['global']['global_seed']

    def n_runs(self):
        return self['global']['seeds']['n_runs']

    def auto_generate_seeds(self):
        return self['global']['seeds']['auto']

    def task_generator_seed(self):
        return self['global']['seeds']['task_generator']

    def agent_seeds(self):
        return self['global']['seeds']['agents']

    def task_generator(self):
        return self['task_generator']

    def tasks_to_bootstrap(self):
        return self['task_generator']['bootstrapping']

    def tasks_to_generate(self):
        return self['task_generator']['tasks_to_generate']

    def features_enabled(self):
        return self['features_enabled']

    def save_properties(self):
        return self['save_properties']

    def penalties(self):
        return self['penalties']

    def functions(self):
        return self['functions']

    def state_features(self):
        return self['state_features']

    def state_window_size(self):
        return self['state']['time_window']

    def context_features(self):
        return self['context_features']

    def global_agent_config(self):
        return self['global_agent_config']

    def agents_config(self):
        return self['agents']
