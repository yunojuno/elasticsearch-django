from os import getenv

from django.core.exceptions import ImproperlyConfigured

DEBUG = True

try:
    from django.db.models import JSONField  # noqa: F401

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": "test.db",
        }
    }
except ImportError:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": getenv("TEST_DB_NAME", "elasticsearch_django"),
            "USER": getenv("TEST_DB_USER", "postgres"),
            "PASSWORD": getenv("TEST_DB_PASSWORD", "postgres"),
            "HOST": getenv("TEST_DB_HOST", "localhost"),
            "PORT": getenv("TEST_DB_PORT", "5432"),
        }
    }

INSTALLED_APPS = (
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.sessions",
    "django.contrib.contenttypes",
    "django.contrib.sites",
    "django.contrib.staticfiles",
    "django.contrib.messages",
    "elasticsearch_django",
    "tests",
)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

SECRET_KEY = "elasticsearch_django"

ROOT_URLCONF = "tests.urls"

APPEND_SLASH = True

STATIC_URL = "/static/"
STATIC_ROOT = "staticfiles"

TIME_ZONE = "UTC"

SITE_ID = 1

###########
# LOGGING #
###########
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(levelname)s %(message)s"}},
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "null": {"level": "DEBUG", "class": "logging.NullHandler"},
    },
    "loggers": {
        "": {"handlers": ["null"], "propagate": True, "level": "DEBUG"},
        "elasticsearch_django": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
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
    },
}

SEARCH_SETTINGS = {
    "connections": {"default": getenv("ELASTICSEARCH_URL")},
    "indexes": {
        # name of the index
        "examples": {
            "models": [
                # model used to populate the index, in app.model format
                "tests.ExampleModel",
            ]
        },
    },
    "settings": {
        # batch size for ES bulk api operations
        "chunk_size": 500,
        # default page size for search results
        "page_size": 25,
        # set to False to prevent automatic signal connections
        "auto_sync": True,
        # List of models which will never auto_sync even if auto_sync is True
        # Use the same app.model format as in 'indexes' above.
        "never_auto_sync": [],
        # retry count used on update in case of a conflict
        "retry_on_conflict": 0,
        "update_strategy": "full",
        # if True, raise ImproperlyConfigured if an index has no mapping file
        "strict_validation": False,
        # path/to/mappings/dir - where mapping files will be expected
        "mappings_dir": "mappings",
    },
}

if not DEBUG:
    raise ImproperlyConfigured("This project is only intended to be used for testing.")
