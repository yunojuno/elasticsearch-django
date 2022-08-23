from django.apps import AppConfig


class TestAppConfig(AppConfig):

    name = "tests"
    verbose_name = "Test App"
    default_auto_field = "django.db.models.AutoField"
