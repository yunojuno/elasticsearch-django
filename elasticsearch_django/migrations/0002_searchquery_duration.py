# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('elasticsearch_django', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='searchquery',
            name='duration',
            field=models.FloatField(default=0, help_text=b'Time taken to execute the search itself, in seconds.'),
            preserve_default=False,
        ),
    ]
