from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


def backfill_legacy_plot_activity(apps, schema_editor):
    GardenPlot = apps.get_model("game", "GardenPlot")
    VerifiedActivity = apps.get_model("game", "VerifiedActivity")

    for plot in GardenPlot.objects.select_related("profile__identity").iterator():
        if not plot.link_url:
            continue
        activity, _created = VerifiedActivity.objects.get_or_create(
            identity=plot.profile.identity,
            kind="published_bookmark",
            canonical_url=plot.link_url,
            defaults={
                "status": "legacy",
                "source_url": plot.link_url,
                "title": plot.link_title,
                "metadata": {"legacy_import": True},
                "verified_at": plot.planted_at,
            },
        )
        plot.verified_activity = activity
        plot.save(update_fields=["verified_activity"])


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0003_increase_url_max_length"),
    ]

    operations = [
        migrations.CreateModel(
            name="SiteScan",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("never", "Never"),
                            ("verified", "Verified"),
                            ("missing_markup", "Missing Markup"),
                            ("missing_feed", "Missing Feed"),
                            ("missing_blogroll", "Missing Blogroll"),
                            ("scan_failed", "Scan Failed"),
                        ],
                        default="never",
                        max_length=32,
                    ),
                ),
                ("scanned_url", models.URLField(blank=True, max_length=2048)),
                ("capabilities", models.JSONField(default=dict)),
                ("issues", models.JSONField(default=list)),
                ("last_error", models.TextField(blank=True)),
                ("last_scanned_at", models.DateTimeField(blank=True, null=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "identity",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="site_scan",
                        to="plants.useridentity",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="VerifiedActivity",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("site_verified", "Site Verified"),
                            ("published_entry", "Published Entry"),
                            ("published_bookmark", "Published Bookmark"),
                            ("blogroll_link", "Blogroll Link"),
                            ("interaction_sent", "Interaction Sent"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("verified", "Verified"),
                            ("legacy", "Legacy"),
                            ("failed", "Failed"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("canonical_url", models.URLField(blank=True, max_length=2048)),
                ("source_url", models.URLField(blank=True, max_length=2048)),
                ("title", models.CharField(blank=True, max_length=500)),
                ("metadata", models.JSONField(default=dict)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "identity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="verified_activities",
                        to="plants.useridentity",
                    ),
                ),
            ],
            options={"ordering": ["-verified_at", "-created_at"]},
        ),
        migrations.CreateModel(
            name="NeighborLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_url", models.URLField(max_length=2048)),
                ("source_url", models.URLField(blank=True, max_length=2048)),
                (
                    "relationship",
                    models.CharField(
                        choices=[("blogroll", "Blogroll"), ("gardn_roll", "Gardn Roll")],
                        default="blogroll",
                        max_length=32,
                    ),
                ),
                ("metadata", models.JSONField(default=dict)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "identity",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="neighbor_links",
                        to="plants.useridentity",
                    ),
                ),
                (
                    "target_identity",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incoming_neighbor_links",
                        to="plants.useridentity",
                    ),
                ),
            ],
            options={"ordering": ["target_url"]},
        ),
        migrations.AddField(
            model_name="gardenplot",
            name="verified_activity",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="garden_plots",
                to="game.verifiedactivity",
            ),
        ),
        migrations.AddConstraint(
            model_name="neighborlink",
            constraint=models.UniqueConstraint(
                fields=("identity", "target_url", "relationship"),
                name="game_unique_neighbor_link",
            ),
        ),
        migrations.RunPython(backfill_legacy_plot_activity, migrations.RunPython.noop),
    ]
