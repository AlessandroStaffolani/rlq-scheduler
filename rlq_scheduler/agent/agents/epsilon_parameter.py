import math


class EpsilonScalar(object):
    """
    Epsilon parameter, scalar version has always the same value
    """

    def __init__(self, value=0.1):
        self.epsilon = value
        self.name = 'scalar'

    def value(self, step=0):
        """
        Returns the current value of epsilon
        Parameters
        ----------
        step: int
            number of step executed
        Returns
        -------
        float
            the value of epsilon
        """
        return self.epsilon

    def __str__(self):
        return '{}_e={}'.format(self.name, str(self.epsilon))


class EpsilonExponentialDecay(EpsilonScalar):
    """
    Epsilon parameter adaptive, it starts from `start` and it will decay exponentially towards `end` with rate `decay`
    """

    def __init__(self, start, end, decay):
        super(EpsilonExponentialDecay, self).__init__(value=start)
        self.start = start
        self.end = end
        self.decay = decay
        self.name = 'exp-decay'

    def value(self, step=0):
        self.epsilon = self.end + (self.start - self.end) * math.exp(-1 * step / self.decay)
        return self.epsilon

    def __str__(self):
        return '{}_es={}_ee={}_ed={}'.format(self.name, str(self.start), str(self.end), str(self.decay))


class EpsilonLinearDecay(EpsilonScalar):
    """
    Linearly decrease epsilon until it react end value
    """

    def __init__(self, start, end, total):
        super(EpsilonLinearDecay, self).__init__(value=start)
        self.start = start
        self.end = end
        self.total = total
        self.name = 'linear-decay'

    def value(self, step=0):
        self.epsilon = self.end + max(0, (self.start - self.end) * ((self.total - step)/self.total))
        return self.epsilon

    def __str__(self):
        return '{}_es={}_ee={}'.format(self.name, str(self.start), str(self.end))


def get_epsilon(type_name='scalar', **kwargs):
    """
    Get the Epsilon parameter from string
    Parameters
    ----------
    type_name: str
        name of the type of epsilon
    kwargs: dict
        parameters for the epsilon class
    Returns
    -------
    EpsilonScalar | EpsilonExponentialDecay
    """
    switcher = {
        'scalar': EpsilonScalar,
        'exp-decay': EpsilonExponentialDecay,
        'linear-decay': EpsilonLinearDecay
    }

    if type_name in switcher:
        if len(kwargs) > 0:
            return switcher[type_name](**kwargs)
        else:
            return switcher[type_name]()
    else:
        return switcher['scalar']()
