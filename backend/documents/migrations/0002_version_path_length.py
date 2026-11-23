from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("documents", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="version",
            name="path",
            field=models.CharField(max_length=128, unique=True),
        ),
    ]
