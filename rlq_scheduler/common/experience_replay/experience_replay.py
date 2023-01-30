import numpy as np

from rlq_scheduler.common.experience_replay import ExperienceEntry


class ExperienceReplay(object):
    """
    ExperienceReplay Class, used by the DQN agents for storing and retrieving samples from the previous sequences of
    iteration with the environment
    """

    def __init__(self,
                 capacity,
                 entry_structure=ExperienceEntry,
                 replacement_policy_name='random',
                 random_state: np.random.RandomState = None):
        """
        Constructor of the ExperienceReplay
        Parameters
        ----------
        capacity: int
            size of the Experience Replay Buffer
        entry_structure: namedtuple
            Structure to use for storing one experience entry in the buffer, it should be a namedtuple. Default is
            ExperienceEntry with the following elements:
                - current_state
                - action
                - reward
                - next_state
        replacement_policy_name: str
            policy to use for the replacement of the entries when the buffer reach the capacity. Default is 'random'.
            Available policies are:
                - 'fifo' remove the first element from the buffer
                - 'random' randomly choose the index to be removed
        """
        self.capacity = capacity
        self.memory = []
        self.entry_structure = entry_structure
        self.replacement_function = replacement_policy(replacement_policy_name)
        if random_state is not None:
            self.random: np.random.RandomState = random_state
        else:
            self.random: np.random.RandomState = np.random.RandomState()

    def push(self, *args):
        """
        Add a new entry to the experience replay buffer
        Parameters
        ----------
        args: list()
            list of arguments to be fed in the `entry_structure` that will be added to the experience replay buffer
        """
        new_entry = self.entry_structure(*args)
        if len(self.memory) < self.capacity or self.capacity == -1:
            # no problem, simply add the experience entry to the memory
            self.memory.append(new_entry)
        else:
            index_to_replace = self.replacement_function(len(self.memory), self.random)
            self.memory[index_to_replace] = new_entry

    def sample(self, batch_size):
        """
        Random choice of `batch_size` elements from the experience replay buffer
        Parameters
        ----------
        batch_size: int
            number of element to be sampled
        Returns
        -------
        list()
            an array with the elements sampled
        """
        indexes = self.random.choice(len(self), batch_size)
        return [self.memory[i] for i in indexes]

    def __len__(self):
        return len(self.memory)

    def __str__(self):
        return '<ExperienceReplay capacity={} size={} >'.format(str(self.capacity), str(len(self)))


def replacement_policy(policy_name):
    """
    Function to retrieve the replacement policy to use in the experience replay
    Parameters
    ----------
    policy_name: str
        name of the policy to use.
        Available policies are:
            - 'fifo' remove the first element from the buffer
            - 'random' randomly choose the index to be removed
    Returns
    -------
    callable
        a function which represent the policy, this function will return the index, from the experience replay buffer,
        to be removed. The function requires as parameter the length of the buffer
    Raises
    ------
    AttributeError
        if the policy name does not match one of the available policies
    """
    switcher = {
        'fifo': fifo_replacement,
        'random': random_replacement
    }
    if policy_name in switcher:
        return switcher[policy_name]
    else:
        raise AttributeError('Replacement policy {} not available')


def fifo_replacement(*args, **kwargs):
    """
    FIFO policy, return the first index
    Parameters
    ----------
    length

    Returns
    -------
    int
        the index
    """
    return 0


def random_replacement(length, random_state, *args, **kwargs):
    """
    Random policy, return a random index
    Parameters
    ----------
    length
    random_state

    Returns
    -------
    int
        the index
    """
    return random_state.randint(0, length)
