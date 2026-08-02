import string

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def setting(name, default=None, required=False, typ=None, description=None, validator=None):
    value = getattr(settings, name, default)

    if required and value is None:
        raise ImproperlyConfigured(
            f"Missing required setting: {name}"
        )
    if validator:
        value = validator(name, value, typ=typ, description=description)

    return value


def bool_validator(name: str, value: str, description: str = None, typ: type = None):
    true_options = ["true", "1"]
    false_options = ["false", "0"]

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        value = str(value)

    value = value.lower()

    if value in true_options and typ == bool:
        return True
    elif value in false_options and typ == bool:
        return False

    raise ImproperlyConfigured(f'''
    {name}: {description}
    type: {typ}
    Invalid {name} value: {value}
    * no case sensitive
    available options: 
                     true:  [ {", ".join(true_options)} ]
                     false: [ {", ".join(false_options)} ]
''')


def env_validator(name: str, value: str, description: str = None, typ: type = None):
    available_options = ['dev', 'stage', 'prod']
    _value = value.lower().strip()

    if _value not in available_options:
        raise ImproperlyConfigured(f'''
        Invalid {name} value: {value}
        available options: [ {", ".join(available_options)} ]
                           [ {", ".join(available_options).upper()} ]'''
                                   )
    return _value


def digits_validator(name: str, value: str, description: str = None, typ: type = None):
    if value not in string.digits:
        raise ImproperlyConfigured(f'''
        Invalid {name} value: {value}
        available options: [ {", ".join(string.digits)} ]''')


RABBITMQ_CONFIG = setting("CDN_RABBITMQ_CONFIG",
                          typ=dict,
                          required=False,
                          description='''RabbitMQ configuration as a dict ex: 
                          {
                               "USER": "",
                               "PASSWORD, "",
                               "HOST", ""
                               "PORT": ""
                          }''')

EXCHANGE_NAME = setting("CDN_EXCHANGE_NAME",
                        typ=str,
                        required=False,
                        description='Exchange Name ex: cdn.events',
                        default='cdn.events')

QUEUE_NAME = setting("CDN_QUEUE_NAME",
                     typ=str,
                     required=False,
                     description='Queue Name ex: pm.events',
                     default='pm.events')

APP_NAME = setting("APP_NAME", typ=str, required=True, default='cdn', description='Application Name')

GRPC_SECURE = setting("CDN_GRPC_SECURE", typ=bool_validator, required=False, default=False,
                      description='Security configuration',
                      validator=bool_validator)

SERVER_ADDRESS = setting("CDN_GRPC_ADDRESS", typ=str, required=True, default='localhost:50051',
                         description='Server address')

REDIS_CACHE = setting(
    "CDN_REDIS_CACHE",
    default="8",
    typ=str,
    validator=digits_validator,
)
