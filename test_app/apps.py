from django.apps import AppConfig


class TestAppConfig(AppConfig):

    """AppConfig for TestApp."""

    name = 'test_app'
    verbose_name = "Test books app"
    configs = []

    def ready(self):
        super().ready()
