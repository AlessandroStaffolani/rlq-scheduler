import numpy as np


def task_generation_events(distribution, tasks_to_generate, rate_per_interval, rate_per_interval_range=None):
    switcher = {
        'none': no_distribution_generation,
        'poisson_fixed': poisson_fixed_distribution_generation,
        'poisson_variable': poisson_variable_distribution_generation
    }
    return switcher[distribution](tasks_to_generate, rate_per_interval, rate_per_interval_range)


def no_distribution_generation(tasks_to_generate, rate_per_interval, rate_per_interval_range=None):
    return np.zeros(tasks_to_generate), None


def poisson_fixed_distribution_generation(tasks_to_generate, rate_per_interval, rate_per_interval_range=None):
    n_intervals = tasks_to_generate // rate_per_interval
    diff = tasks_to_generate % rate_per_interval
    rate_per_second = rate_per_interval / 60
    exp_scale = 1 / rate_per_second
    events = np.random.exponential(exp_scale, rate_per_interval * n_intervals)
    if diff != 0:
        events = np.append(events, np.random.exponential(exp_scale, diff))
    return events, rate_per_interval


def poisson_variable_distribution_generation(tasks_to_generate, rate_per_interval, rate_per_interval_range):
    rates = []
    events = np.array([])
    while events.shape[0] < tasks_to_generate:
        rate_per_minute = np.random.randint(rate_per_interval_range[0], rate_per_interval_range[1])
        total = rate_per_minute
        if events.shape[0] + rate_per_minute > tasks_to_generate:
            total = tasks_to_generate - events.shape[0]
        events = np.append(events, poisson_fixed_distribution_generation(total, rate_per_minute)[0])
        rates.append(rate_per_minute)
    return events, rates


def generate_events_google_traces(tasks_to_generate, rate_per_interval, random_generator, time_multiplier=1):
    n_intervals = tasks_to_generate // rate_per_interval
    diff = tasks_to_generate % rate_per_interval
    exp_scale = time_multiplier / rate_per_interval
    events = random_generator.exponential(exp_scale, rate_per_interval * n_intervals)
    if diff != 0:
        events = np.append(events, random_generator.exponential(exp_scale, diff))
    return events

