from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="SearchQuery",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                (
                    "index",
                    models.CharField(
                        default="_all",
                        help_text="The name of the ElasticSearch index(es) being queried.",
                        max_length=100,
                    ),
                ),
                (
                    "query",
                    models.TextField(
                        default="{}", help_text="The raw ElasticSearch DSL query."
                    ),
                ),
                (
                    "hits",
                    models.TextField(
                        default="{}",
                        help_text="The list of meta info for each of the query matches returned.",
                    ),
                ),
                (
                    "total_hits",
                    models.IntegerField(
                        default=0,
                        help_text="Total number of matches found for the query (!= the hits returned).",
                    ),
                ),
                (
                    "reference",
                    models.CharField(
                        default="",
                        help_text="Custom reference used to identify and group related searches.",
                        max_length=100,
                        blank=True,
                    ),
                ),
                (
                    "executed_at",
                    models.DateTimeField(
                        help_text="When the search was executed - set via execute() method."
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        related_name="search_queries",
                        blank=True,
                        to=settings.AUTH_USER_MODEL,
                        help_text="The user who made the search query (nullable).",
                        null=True,
                        on_delete=models.SET_NULL,
                    ),
                ),
            ],
        )
    ]
