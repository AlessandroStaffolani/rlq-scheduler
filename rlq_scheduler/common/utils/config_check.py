
from rlq_scheduler.common.exceptions import ConfigException


def check_config(config, required_fields=None, defualt_fields=None):
    if required_fields is None and defualt_fields is None:
        return config

    missing_fields = []
    for item in required_fields:
        if not is_field_present(config, item['field'], item['type']):
            missing_fields.append(item)

    if len(missing_fields) > 0:
        raise ConfigException(fields=missing_fields)

    for item in defualt_fields:
        add_default_value(config, item['field'], item['value'])


def is_field_present(root, field, field_types):
    sub_fields = field.split('.')
    tmp = root
    for sub in sub_fields:
        if tmp is not None and sub in tmp:
            tmp = tmp[sub]
        else:
            return False
    type_is_valid = False
    if isinstance(field_types, list):
        for t in field_types:
            if isinstance(tmp, t):
                type_is_valid = True
    else:
        if isinstance(tmp, field_types):
            type_is_valid = True
    return type_is_valid


def add_default_value(root, field, value):
    sub_fields = field.split('.')
    tmp = root
    for i, sub in enumerate(sub_fields):
        if i < len(sub_fields) - 1:
            if isinstance(tmp, dict) and sub in tmp:
                tmp = tmp[sub]
            else:
                tmp[sub] = {}
                tmp = tmp[sub]
        else:
            if sub not in tmp:
                tmp[sub] = value
            else:
                if tmp[sub] is None:
                    tmp[sub] = value
