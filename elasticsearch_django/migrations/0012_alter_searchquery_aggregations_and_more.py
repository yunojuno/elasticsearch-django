# Generated by Django 4.1.4 on 2022-12-20 13:00

import django.core.serializers.json
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("elasticsearch_django", "0011_searchquery_aggregations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="searchquery",
            name="aggregations",
            field=models.JSONField(
                blank=True,
                default=dict,
                encoder=django.core.serializers.json.DjangoJSONEncoder,
                help_text="The raw aggregations returned from the query.",
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="searchquery",
            name="hits",
            field=models.JSONField(
                blank=True,
                encoder=django.core.serializers.json.DjangoJSONEncoder,
                help_text="The list of meta info for each of the query matches returned.",
                null=True,
            ),
        ),
    ]