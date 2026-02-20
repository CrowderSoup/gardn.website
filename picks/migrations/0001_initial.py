from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("plants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Pick",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "picked",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="incoming_picks", to="plants.useridentity"),
                ),
                (
                    "picker",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="outgoing_picks", to="plants.useridentity"),
                ),
            ],
            options={},
        ),
        migrations.AddConstraint(
            model_name="pick",
            constraint=models.UniqueConstraint(fields=("picker", "picked"), name="unique_picker_pair"),
        ),
    ]
