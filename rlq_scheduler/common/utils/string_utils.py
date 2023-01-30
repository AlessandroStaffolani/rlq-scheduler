import re


def camel_to_snake(value):
    pattern = re.compile(r'(?<!^)(?=[A-Z])')
    return pattern.sub('_', value).lower()


def snake_to_camel(value):
    return ''.join(word.title() for word in value.split('_'))

