# -*- coding: utf-8 -*-
"""django_elasticsearch default test settings."""
from os import getenv

DEBUG = True

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': 'test.db',
    }
}

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.sites',
    'elasticsearch_django',
)

MIDDLEWARE_CLASSES = [
]

SECRET_KEY = "elasticsearch_django"

ROOT_URLCONF = 'urls'

APPEND_SLASH = True

STATIC_URL = '/static/'

TIME_ZONE = 'UTC'

SITE_ID = 1

assert DEBUG is True, "This project is only intended to be used for testing."


###########
# LOGGING #
###########
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        # 'verbose': {
        #     'format': '%(levelname)s %(asctime)s %(module)s %(process)d %(thread)d %(message)s'
        # },
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'null': {
            'level': 'DEBUG',
            'class': 'django.utils.log.NullHandler',
        },
    },
    'loggers': {
        '': {
            'handlers': ['null'],
            'propagate': True,
            'level': 'DEBUG',
        },
        # 'django': {
        #     'handlers': ['console'],
        #     'level': getenv('LOGGING_LEVEL_DJANGO', 'WARNING'),
        #     'propagate': False,
        # },
        # 'django.db.backends': {
        #     'level': 'ERROR',
        #     'handlers': ['console'],
        #     'propagate': False,
        # },
        'elasticsearch_django': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        # 'elasticsearch': {
        #     'handlers': ['console'],
        #     'level': getenv('LOGGING_LEVEL_SEARCH', 'WARNING'),
        #     'propagate': False,
        # },
        # 'elasticsearch.trace': {
        #     'handlers': ['console'],
        #     'level': getenv('LOGGING_LEVEL_SEARCH', 'WARNING'),
        #     'propagate': False,
        # },
        # 'requests': {
        #     'handlers': ['console'],
        #     'level': getenv('LOGGING_LEVEL_REQUESTS', 'WARNING'),
        #     'propagate': False,
        # },
        # 'requests.packages.urllib3': {
        #     'handlers': ['console'],
        #     'level': getenv('LOGGING_LEVEL_REQUESTS', 'WARNING'),
        #     'propagate': False,
        # },
        # 'urllib3': {
        #     'handlers': ['console'],
        #     'level': getenv('LOGGING_LEVEL_REQUESTS', 'WARNING'),
        #     'propagate': False,
        # },
    }
}

SEARCH_SETTINGS = {
    'connections': {
        'default': getenv('ELASTICSEARCH_URL'),
    },
    'indexes': {
        # # name of the index
        # 'articles': {
        #     'models': [
        #         # model used to populate the index, in app.model format
        #         'app.Model',
        #     ]
        # },
    },
    'settings': {
        # batch size for ES bulk api operations
        'chunk_size': 500,
        # default page size for search results
        'page_size': 25,
        # set to False to prevent automatic signal connections
        'auto_sync': True,
        # if True, raise ImproperlyConfigured if an index has no mapping file
        'strict_validation': False,
        # path/to/mappings/dir - where mapping files will be expected
        'mappings_dir': 'mappings'
    }
}
