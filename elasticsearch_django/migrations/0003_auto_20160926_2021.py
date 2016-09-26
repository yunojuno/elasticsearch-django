# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('elasticsearch_django', '0002_searchquery_duration'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='searchquery',
            options={'verbose_name': 'Search query', 'verbose_name_plural': 'Search queries'},
        ),
    ]
