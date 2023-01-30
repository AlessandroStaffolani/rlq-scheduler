import numpy as np
from copy import deepcopy


class ActionSpace(object):
    """
    Action Space class, it represents the action space of the agent
    """

    def __init__(self, actions, external_workers_config=None):
        # protected properties
        self._external_workers_config = external_workers_config
        self._actions = self._create_action_space(actions)

    def size(self):
        """
        Get the size of the action space
        Returns
        -------
        int
            the size
        """
        return self._actions.size

    def get_actions(self):
        """
        Get the action space as list
        Returns
        -------
        list()
            the action space as a list
        """
        return deepcopy(self._actions.tolist())

    def get_action(self, index):
        """
        Get the value of an action from the action space using the index
        Parameters
        ----------
        index: int
            index of the action
        Returns
        -------
        str
            action value
        """
        return self._actions[index]

    def get_action_index(self, action: str):
        return self._actions.tolist().index(action)

    def is_external_worker_enabled(self):
        """
        Return True if the external worker feature is enabled, False otherwise
        Returns
        -------
        bool
        """
        if self._external_workers_config is None or self._external_workers_config['enabled'] is False:
            return False
        else:
            return True

    def get_external_worker_prefix(self):
        """
        if the external worker feature is enabled, return the prefix used in the actions, otherwise return None
        Returns
        -------
        str | None
        """
        if self._external_workers_config is None and self._external_workers_config['enabled'] is False:
            return None
        else:
            return self._external_workers_config['action_prefix']

    def _create_action_space(self, default_actions):
        """
        Create the action space of the agent, based on the _external_workers_config property. If the property is None
        the action space is given by the default_action_space. Otherwise, the action space is the default_action_space
        plus the action with the prefix
        Parameters
        ----------
        default_actions: list()
            list of actions available
        Returns
        -------
        numpy.ndarray with the final action space
        """
        if self.is_external_worker_enabled():
            # external_worker feature is enabled
            prefix = self.get_external_worker_prefix()
            action_space = []
            action_space.extend(default_actions)
            for action in default_actions:
                action_space.append(prefix + '_' + action)
            return np.array(action_space)
        else:
            # external_worker feature is not enabled
            return np.array(default_actions)

    def __iter__(self):
        return iter(self._actions)

    def __len__(self):
        return self.size()

    def __str__(self):
        return '<ActionSpace use_external={} actions={}>'\
            .format(str(self.is_external_worker_enabled()), str(self._actions))
