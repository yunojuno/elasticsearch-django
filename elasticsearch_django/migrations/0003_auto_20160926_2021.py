from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("elasticsearch_django", "0002_searchquery_duration")]

    operations = [
        migrations.AlterModelOptions(
            name="searchquery",
            options={
                "verbose_name": "Search query",
                "verbose_name_plural": "Search queries",
            },
        )
    ]
