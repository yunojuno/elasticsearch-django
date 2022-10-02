from uuid import uuid4

from django.conf import settings
from django.db import models

from elasticsearch_django.models import (
    SearchDocumentManagerMixin,
    SearchDocumentMixin,
    SearchResultsQuerySet,
)


class ExampleModelQuerySet(SearchResultsQuerySet):
    pass


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

    objects = ExampleModelManager.from_queryset(ExampleModelQuerySet)()

    def get_search_document_id(self) -> str:
        return f"{self.simple_field_1}_{self.simple_field_2}"

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


# === Compound models ===


class ModelAQuerySet(SearchResultsQuerySet):
    # this is the field used as the ID for the search documents
    search_document_id_field = "field_1"


class ModelA(models.Model):
    field_1 = models.UUIDField(default=uuid4)
    field_2 = models.CharField(max_length=100)
    objects = ModelAQuerySet.as_manager()


class ModelB(SearchDocumentMixin, models.Model):

    source = models.OneToOneField(ModelA, on_delete=models.CASCADE)

    def get_search_document_id(self) -> str:
        return str(self.source.field_1)

    def as_search_document(self, *, index: str) -> dict:
        return {"field_2": self.source.field_2, "extra_info": "some other data"}
