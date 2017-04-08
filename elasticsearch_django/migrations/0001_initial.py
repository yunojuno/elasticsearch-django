# -*- coding: utf-8 -*-


from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='SearchQuery',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('index', models.CharField(default=b'_all', help_text=b'The name of the ElasticSearch index(es) being queried.', max_length=100)),
                ('query', models.TextField(default=b'{}', help_text=b'The raw ElasticSearch DSL query.')),
                ('hits', models.TextField(default=b'{}', help_text=b'The list of meta info for each of the query matches returned.')),
                ('total_hits', models.IntegerField(default=0, help_text=b'Total number of matches found for the query (!= the hits returned).')),
                ('reference', models.CharField(default=b'', help_text=b'Custom reference used to identify and group related searches.', max_length=100, blank=True)),
                ('executed_at', models.DateTimeField(help_text=b'When the search was executed - set via execute() method.')),
                ('user', models.ForeignKey(related_name='search_queries', blank=True, to=settings.AUTH_USER_MODEL, help_text=b'The user who made the search query (nullable).', null=True)),
            ],
        ),
    ]
