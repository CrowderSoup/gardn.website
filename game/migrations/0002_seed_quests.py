from __future__ import annotations

from django.db import migrations


INITIAL_QUESTS = [
    {
        "slug": "ten-links-deep",
        "title": "Ten Links Deep",
        "description": "Harvest 10 links from the world.",
        "category": "indieweb",
        "order": 1,
        "requirements": {},
        "rewards": {"xp": 50, "unlock_area": "ruins"},
        "npc_id": "wanderer",
    },
    {
        "slug": "plant-your-flag",
        "title": "Plant Your Flag",
        "description": "Get your first website online.",
        "category": "tutorial",
        "order": 2,
        "requirements": {},
        "rewards": {"xp": 100, "unlock_area": "garden_expansion"},
        "npc_id": "elder_aldyn",
    },
    {
        "slug": "good-neighbor",
        "title": "Good Neighbor",
        "description": "Pick a plant from 3 different gardens.",
        "category": "community",
        "order": 3,
        "requirements": {"min_picks": 3},
        "rewards": {"xp": 75, "plant_type": "rare_seed"},
        "npc_id": "wanderer",
    },
    {
        "slug": "write-something",
        "title": "Write Something",
        "description": "Post to your site and register the link.",
        "category": "indieweb",
        "order": 4,
        "requirements": {"requires_website": True},
        "rewards": {"xp": 150, "unlock_area": "library"},
        "npc_id": "archivist",
    },
    {
        "slug": "webring-rider",
        "title": "Webring Rider",
        "description": "Follow a webring link to a new garden.",
        "category": "community",
        "order": 5,
        "requirements": {},
        "rewards": {"xp": 100, "unlock_area": "eastern_path"},
        "npc_id": "wanderer",
    },
    {
        "slug": "deep-roots",
        "title": "Deep Roots",
        "description": "Keep a plant alive for 7 days (water daily).",
        "category": "indieweb",
        "order": 6,
        "requirements": {"days_alive": 7},
        "rewards": {"xp": 200, "unlock_area": "greenhouse"},
        "npc_id": "elder_aldyn",
    },
]


def seed_quests(apps, schema_editor):
    Quest = apps.get_model("game", "Quest")
    for quest_data in INITIAL_QUESTS:
        Quest.objects.get_or_create(slug=quest_data["slug"], defaults=quest_data)


def unseed_quests(apps, schema_editor):
    Quest = apps.get_model("game", "Quest")
    Quest.objects.filter(slug__in=[q["slug"] for q in INITIAL_QUESTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("game", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_quests, unseed_quests),
    ]
