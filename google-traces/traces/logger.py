import datetime
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from dateutil.tz import tzutc, tzlocal

from traces.filesystem import get_absolute_path


class Iso8601UTCTimeFormatter(logging.Formatter):
    """
    A logging Formatter class giving timestamps in a more common ISO 8601 format.
    The default logging.Formatter class **claims** to give timestamps in ISO 8601 format
    if it is not initialized with a different timestamp format string.  However, its
    format, "YYYY-MM-DD hh:mm:ss,sss", is much less common than, "YYYY-MM-DDThh:mm:ss.sss".
    That is, the separator between date and time is a space instead of the letter "T"
    and the separator for fractional seconds is a comma instead of a period (full stop).
    While these differences may not be strictly *wrong*, it makes the formatted timestamp
    *unusual*.
    This formatter class removes some of the differences by using Python's own
    datetime.datetime.isoformat() method.  That method uses "T" as the default separator
    between date and time.  And it always uses a period (full stop) for fractional
    seconds, even if a comma is normally used for fractional numbers in the current
    locale.
    """

    def __init__(self, log_format=None, time_format=None, time_zone='UTC'):
        """
        The purpose of this constructor is to set the timezone.

        :param log_format: Log record formatting string.
        :type log_format: str
        :param time_format: Time formatting string. You probably **DO NOT** want one.
        :type time_format: str
        :type time_zone: str time zone to set for the logger time
        """
        super(Iso8601UTCTimeFormatter, self).__init__(log_format, time_format)

        if time_zone == 'local':
            self._TIMEZONE = tzlocal()
        else:
            self._TIMEZONE = tzutc()

    def formatTime(self, record, time_format=None):
        """
        In the event that a timeFormat string is given, this method will use the
        formatTime() method of the superclass (logging.Formatter) instead.  That's
        because this method doesn't need timeFormat. So, other than this solution,
        the options for handling that argument were to ignore it or raise an exception,
        either of which probably violate the principle of least astonishment (POLA).
        :param record: Record of the current log entry
        :type record: logging.LogRecord
        :param time_format: Time formatting string. You probably **DO NOT** want one.
        :type time_format: str
        :return: Log record's timestamp in ISO 8601 format
        :rtype: str or unicode
        """
        if time_format is not None:
            return super(Iso8601UTCTimeFormatter, self).formatTime(record, time_format)

        return datetime.datetime.fromtimestamp(record.created, self._TIMEZONE).isoformat()


FORMATTER = Iso8601UTCTimeFormatter(
    "%(asctime)s | %(name)s | (%(processName)-10s) | (%(threadName)-10s) | %(levelname)s | %(message)s",
    time_zone='local')


def get_console_handler():
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(FORMATTER)
    return console_handler


def get_file_handler(level, log_basepath='logs'):
    base_path = get_absolute_path(log_basepath)
    if not os.path.exists(base_path):
        os.mkdir(base_path)
    filename = logging.getLevelName(level).lower()
    full_filepath = os.path.join(base_path, f'{filename}.log')
    file_handler = RotatingFileHandler(full_filepath, maxBytes=1024*1024*10, backupCount=5)
    file_handler.setFormatter(FORMATTER)
    file_handler.setLevel(level)
    return file_handler


HANDLER_MAPPER = {
    'console': get_console_handler,
    'file': get_file_handler
}

LEVELS = [
    logging.DEBUG,
    logging.INFO,
    logging.WARNING,
    logging.ERROR
]

LOGGER_CONFIG_DEFAULT = {
    'name': 'traces',
    'level': 10,
    'handlers': [
        {
            'type': 'console',
            'parameters': None
        },
        {
            'type': 'file',
            'parameters':
                {
                    'log_basepath': 'logs'
                }
        }
    ]
}


def _get_logger(logger_config=None) -> logging.Logger:
    if logger_config is not None and 'name' in logger_config:
        logger_name = logger_config['name']
    else:
        logger_name = 'logger'
    logger = logging.getLogger(logger_name)

    if len(logger.handlers) == 0:
        if logger_config is None and 'handlers' in logger_config:
            logger.addHandler(get_console_handler())
        else:
            logger.setLevel(logger_config['level'])
            handlers_config = logger_config['handlers']
            for handler_config in handlers_config:
                if handler_config['type'] == 'console':
                    handler = get_console_handler()
                    logger.addHandler(handler)
                elif handler_config['type'] == 'file':
                    for level in LEVELS:
                        handler = get_file_handler(level, **handler_config['parameters'])
                        logger.addHandler(handler)
                else:
                    raise AttributeError(
                        'handler type {} is not valid. Check logger_config'.format(handler_config['type']))

        # with this pattern, it's rarely necessary to propagate the error up to parent
        logger.propagate = False

    return logger


class BaseLogger(logging.Logger):

    def __init__(self, logger_config=None):
        if logger_config is not None and 'name' in logger_config:
            name = logger_config['name']
        else:
            name = 'logger'
        if logger_config is not None and 'level' in logger_config:
            level = logger_config['level']
        else:
            level = logging.INFO
        super(BaseLogger, self).__init__(name, level)
        self._set_handler(logger_config)
        # with this pattern, it's rarely necessary to propagate the error up to parent
        self.propagate = False
        self.logger_config = logger_config

    def _log(self, level, msg, args, exc_info=None, extra=None, stack_info=False, **kwargs):
        super()._log(level, msg, args, exc_info, extra, stack_info)

    def _set_handler(self, logger_config):
        if len(self.handlers) == 0:
            for handler_config in logger_config['handlers']:
                if handler_config['type'] == 'console':
                    handler = get_console_handler()
                    self.addHandler(handler)
                elif handler_config['type'] == 'file':
                    for level in LEVELS:
                        handler = get_file_handler(level, **handler_config['parameters'])
                        self.addHandler(handler)
                else:
                    raise AttributeError(
                        'handler type {} is not valid. Check logger_config'.format(handler_config['type']))

    def close(self):
        for handler in self.handlers:
            self.removeHandler(handler)
            handler.close()


def get_logger(logger_config=None) -> 'BaseLogger':
    config = logger_config if logger_config is not None else LOGGER_CONFIG_DEFAULT
    return BaseLogger(config)


logger = get_logger()
