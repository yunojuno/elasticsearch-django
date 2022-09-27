from django.conf import settings
from django.db import models

from elasticsearch_django.models import SearchDocumentManagerMixin, SearchDocumentMixin


class ExampleModelManager(SearchDocumentManagerMixin, models.Manager):
    def get_search_queryset(self, index="_all"):
        return self.all()


class ExampleModel(SearchDocumentMixin, models.Model):
    """Model class for use in tests."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True
    )
    simple_field_1 = models.IntegerField()
    simple_field_2 = models.CharField(max_length=100)
    complex_field = models.FileField()

    objects = ExampleModelManager()

    def user_name(self) -> str:
        return self.user.get_full_name() if self.user else "Anonymous"

    def as_search_document(self, index="_all"):
        return {
            "simple_field_1": self.simple_field_1,
            "simple_field_2": self.simple_field_2,
            "complex_field": str(self.complex_field),
            "user_name": self.user_name(),
        }


class ExampleModelWithCustomPrimaryKey(SearchDocumentMixin, models.Model):
    """Model class with a custom primary key for use in tests."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True
    )
    simple_field_1 = models.IntegerField(primary_key=True)
    simple_field_2 = models.CharField(max_length=100)
    complex_field = models.FileField()

    objects = ExampleModelManager()

    def user_name(self) -> str:
        return self.user.get_full_name() if self.user else "Anonymous"

    def as_search_document(self, index="_all"):
        return {
            "simple_field_1": self.simple_field_1,
            "simple_field_2": self.simple_field_2,
            "complex_field": str(self.complex_field),
            "user_name": self.user_name(),
        }
