from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("plants", "0006_remove_useridentity_svg_cache"),
        ("game", "0005_increase_garden_plot_title_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="GardenVisit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("visited_on", models.DateField()),
                (
                    "source",
                    models.CharField(
                        choices=[("neighbor_grove", "Neighbor Grove"), ("shared_link", "Shared Link")],
                        default="neighbor_grove",
                        max_length=32,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "host",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="hosted_garden_visits",
                        to="plants.useridentity",
                    ),
                ),
                (
                    "visitor",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="garden_visits",
                        to="plants.useridentity",
                    ),
                ),
            ],
            options={
                "ordering": ["-visited_on", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="gardenvisit",
            constraint=models.UniqueConstraint(
                fields=("host", "visitor", "visited_on"),
                name="game_unique_daily_garden_visit",
            ),
        ),
    ]
