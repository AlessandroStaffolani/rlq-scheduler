import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# set up matplotlib
from rlq_scheduler.common.stats import RunStats

IS_IPYTHON = 'inline' in matplotlib.get_backend()

DEFAULT_FIG_SIZE = (12, 12)


def plot_array(data,
               title,
               xlabel='x',
               ylabel='y',
               legend=None,
               figsize=DEFAULT_FIG_SIZE,
               loc='upper center',
               bbox_to_anchor=(0.5, 1.05),
               return_plot=False):
    """
    Plot total reward per time step
    Parameters
    ----------
    data: list()
        list of rewards values
    title: str
        title for the plot
    xlabel: str
        x label name
    ylabel: str
        y label name
    legend: str | list() | None
        legend of the plot, if None no legend is added
    figsize: tuple()
        tuple with the size of the figure generate, default (8, 8)
    loc: str | None
        localization of the legend in the plot
    bbox_to_anchor: tuple | None
        position of the legend in the plot
    return_plot: bool
        if True it return the plot instead of showing it
    """
    fig1 = plt.figure(figsize=figsize)
    plt.plot(data)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    if legend is not None:
        plt.legend(legend, loc=loc, bbox_to_anchor=bbox_to_anchor, shadow=True, fancybox=True)
    if return_plot:
        return fig1
    else:
        if IS_IPYTHON:
            plt.show(fig1)
        else:
            plt.show()


def plot_array_with_smoothed(data,
                             title,
                             xlabel='x',
                             ylabel='y',
                             legend=None,
                             window_size=50,
                             figsize=DEFAULT_FIG_SIZE,
                             loc='upper center',
                             bbox_to_anchor=(0.5, 1.05),
                             return_plot=False
                             ):
    df = pd.DataFrame(data)
    rolling = df[0].rolling(window_size, win_type='gaussian', center=True).mean(std=data.std())
    fig1 = plt.figure(figsize=figsize)
    plt.plot(df[0], 'lightblue', rolling, 'b')
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    if legend is not None:
        plt.legend(legend, loc=loc, bbox_to_anchor=bbox_to_anchor, shadow=True, fancybox=True)
    if return_plot:
        return fig1
    else:
        if IS_IPYTHON:
            plt.show(fig1)
        else:
            plt.show()


def plot_array_and_smoothed(data, title,
                            xlabel='x',
                            ylabel='y',
                            legend=None,
                            window_size=50,
                            figsize=DEFAULT_FIG_SIZE,
                            loc='upper center',
                            bbox_to_anchor=(0.5, 1.05)):
    fig, axs = plt.subplots(1, 2, figsize=figsize)
    fig.suptitle(title)
    df = pd.DataFrame(data)
    rolling = df[0].rolling(window_size, win_type='gaussian', center=True).mean(std=data.std())
    axs[0].plot(data)
    axs[0].set_title(f'Not smoothed')
    axs[0].set(xlabel=xlabel, ylabel=ylabel)
    axs[1].plot(df[0], 'lightblue', rolling, 'b')
    axs[1].set_title(f'Smoothed')
    axs[1].set(xlabel=xlabel, ylabel=ylabel)

    # Hide x labels and tick labels for top plots and y ticks for right plots.
    for ax in axs.flat:
        ax.label_outer()
    if legend is not None:
        plt.legend(legend, loc=loc, bbox_to_anchor=bbox_to_anchor, shadow=True, fancybox=True)
    if IS_IPYTHON:
        plt.show(fig)
    else:
        plt.show()


def plot_run_stats(stats: RunStats, name='', figsize=(8, 6), smooth_loss=False, window_size=50, double_view=False,
                   param_name=None):
    reward = np.cumsum(np.array(stats.execution_history_stats['reward'], dtype=np.float))
    stats_params = ""
    if param_name is not None:
        stats_params = f"seed: {stats.agent_stats['agent_parameters']['agent_seed']}"
        stats_params += f" {param_name}: {stats.agent_stats['agent_parameters'][param_name]}"
        stats_params += f" reward multiplier: {stats.agent_stats['agent_parameters']['reward_multiplier']}"

    plot_array(reward, f"{name} total reward {stats_params}", "Time", "Total reward", figsize=figsize)
    if stats.global_stats['validation_reward'] is not None:
        validation_reward = np.zeros(len(stats.global_stats['validation_reward']), dtype=np.float)
        for i, arr in enumerate(stats.global_stats['validation_reward']):
            if np.isnan(arr[-1]):
                np_arr = np.array(arr[0:-1], dtype=np.float)
            else:
                np_arr = np.array(arr, dtype=np.float)
            validation_reward[i] = np_arr.mean()
        plot_array(validation_reward, f"{name} validation reward {stats_params}", "Time", "Avg reward", figsize=figsize)
    else:
        validation_reward = None
    if stats.execution_history_stats['loss'] is not None:
        loss = np.array(stats.execution_history_stats['loss'], dtype=np.float)
        if smooth_loss:
            if double_view:
                plot_array_and_smoothed(loss, f"{name} training loss {stats_params}", "Time", "loss",
                                        window_size=window_size, figsize=(16, 6))
            else:
                plot_array_with_smoothed(loss, f"{name} training loss {stats_params}", "Time", "loss",
                                         window_size=window_size, figsize=figsize)
        else:
            plot_array(loss, f"{name} training loss {stats_params}", "Time", "loss", figsize=figsize)
    else:
        loss = None
    if stats.execution_history_stats['epsilon'] is not None:
        epsilon = np.array(stats.execution_history_stats['epsilon'], dtype=np.float)
        plot_array(epsilon, f"{name} epsilon {stats_params}", "Time", "Epsilon", figsize=figsize)
    else:
        epsilon = None
    return reward, validation_reward, loss, epsilon


def multi_plot(values: list, titles, sup_title, xlabel, ylabel, rows=1, columns=1, legend=None,
               figsize=DEFAULT_FIG_SIZE,
               loc='upper center',
               bbox_to_anchor=(0.5, 1.05)):
    fig, axs = plt.subplots(rows, columns, figsize=figsize)
    fig.suptitle(sup_title)
    count = 0
    if rows > 1:
        for i in range(rows):
            for j in range(columns):
                axs[i, j].plot(values[count])
                axs[i, j].set_title(titles[count])
                count += 1
    else:
        for j in range(columns):
            axs[j].plot(values[count])
            axs[j].set_title(titles[count])
            count += 1

    for ax in axs.flat:
        ax.set(xlabel=xlabel, ylabel=ylabel)

    # Hide x labels and tick labels for top plots and y ticks for right plots.
    for ax in axs.flat:
        ax.label_outer()
    if legend is not None:
        plt.legend(legend, loc=loc, bbox_to_anchor=bbox_to_anchor, shadow=True, fancybox=True)
    if IS_IPYTHON:
        plt.show(fig)
    else:
        plt.show()


def plot_hyperparameter_tuning_results(results,
                                       x,
                                       y,
                                       hue,
                                       xlabel,
                                       ylabel,
                                       title,
                                       figsize=(12, 8),
                                       legend=True):
    plt.figure(figsize=figsize)

    plot = sns.boxplot(x=x, y=y, hue=hue, data=results)
    if legend:
        plt.legend(bbox_to_anchor=(1.05, 1), loc=2, borderaxespad=0., fancybox=False, framealpha=1, borderpad=1)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.title(title)
    return plot


def plot_array_population(array, title, xlabel='', ylabel='', perc=0.8, figsize=(20, 7), sort_descending=False):
    df = pd.DataFrame({'array': array, 't': np.arange(0, array.shape[0])})
    if sort_descending:
        ordered = -np.sort(-array)
    else:
        ordered = np.sort(array)
    df_percentile = pd.DataFrame(
        {
            'array': ordered[0:int(array.shape[0] * perc)], 't': np.arange(0, int(array.shape[0] * perc))
        }
    )
    plt.figure(figsize=figsize)
    plot_full = sns.boxplot(x=df['array'])
    plt.title(f'Whole population for {title}')
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.figure(figsize=figsize)
    plot_percentile = sns.boxplot(x=df_percentile['array'])
    plt.title(f'{int(perc*100)}th percentile population for {title}')
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    return plot_full, plot_percentile

