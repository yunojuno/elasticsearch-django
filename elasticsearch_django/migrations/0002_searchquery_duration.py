from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("elasticsearch_django", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="searchquery",
            name="duration",
            field=models.FloatField(
                default=0,
                help_text="Time taken to execute the search itself, in seconds.",
            ),
            preserve_default=False,
        )
    ]
