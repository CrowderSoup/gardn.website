from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0004_site_evidence"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gardenplot",
            name="link_title",
            field=models.CharField(blank=True, max_length=500),
        ),
    ]
