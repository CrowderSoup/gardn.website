from __future__ import annotations

from django.db import models


class SiteScan(models.Model):
    """Latest known scan result for a player's website."""

    STATUS_NEVER = "never"
    STATUS_VERIFIED = "verified"
    STATUS_MISSING_MARKUP = "missing_markup"
    STATUS_MISSING_FEED = "missing_feed"
    STATUS_MISSING_BLOGROLL = "missing_blogroll"
    STATUS_SCAN_FAILED = "scan_failed"

    STATUS_CHOICES = [
        (STATUS_NEVER, "Never"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_MISSING_MARKUP, "Missing Markup"),
        (STATUS_MISSING_FEED, "Missing Feed"),
        (STATUS_MISSING_BLOGROLL, "Missing Blogroll"),
        (STATUS_SCAN_FAILED, "Scan Failed"),
    ]

    identity = models.OneToOneField(
        "plants.UserIdentity",
        on_delete=models.CASCADE,
        related_name="site_scan",
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_NEVER,
    )
    scanned_url = models.URLField(max_length=2048, blank=True)
    capabilities = models.JSONField(default=dict)
    issues = models.JSONField(default=list)
    last_error = models.TextField(blank=True)
    last_scanned_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"SiteScan({self.identity}, {self.status})"


class VerifiedActivity(models.Model):
    """A game-relevant activity that is pending, verified, or legacy-imported."""

    KIND_SITE_VERIFIED = "site_verified"
    KIND_PUBLISHED_ENTRY = "published_entry"
    KIND_PUBLISHED_BOOKMARK = "published_bookmark"
    KIND_BLOGROLL_LINK = "blogroll_link"
    KIND_INTERACTION_SENT = "interaction_sent"

    KIND_CHOICES = [
        (KIND_SITE_VERIFIED, "Site Verified"),
        (KIND_PUBLISHED_ENTRY, "Published Entry"),
        (KIND_PUBLISHED_BOOKMARK, "Published Bookmark"),
        (KIND_BLOGROLL_LINK, "Blogroll Link"),
        (KIND_INTERACTION_SENT, "Interaction Sent"),
    ]

    STATUS_PENDING = "pending"
    STATUS_VERIFIED = "verified"
    STATUS_LEGACY = "legacy"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_LEGACY, "Legacy"),
        (STATUS_FAILED, "Failed"),
    ]

    identity = models.ForeignKey(
        "plants.UserIdentity",
        on_delete=models.CASCADE,
        related_name="verified_activities",
    )
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    canonical_url = models.URLField(max_length=2048, blank=True)
    source_url = models.URLField(max_length=2048, blank=True)
    title = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-verified_at", "-created_at"]

    def __str__(self) -> str:
        return self.title or self.canonical_url or f"{self.kind}:{self.identity_id}"


class NeighborLink(models.Model):
    """Verified link between one Gardn identity and another."""

    RELATIONSHIP_BLOGROLL = "blogroll"
    RELATIONSHIP_GARDN_ROLL = "gardn_roll"

    RELATIONSHIP_CHOICES = [
        (RELATIONSHIP_BLOGROLL, "Blogroll"),
        (RELATIONSHIP_GARDN_ROLL, "Gardn Roll"),
    ]

    identity = models.ForeignKey(
        "plants.UserIdentity",
        on_delete=models.CASCADE,
        related_name="neighbor_links",
    )
    target_identity = models.ForeignKey(
        "plants.UserIdentity",
        on_delete=models.CASCADE,
        related_name="incoming_neighbor_links",
        null=True,
        blank=True,
    )
    target_url = models.URLField(max_length=2048)
    source_url = models.URLField(max_length=2048, blank=True)
    relationship = models.CharField(
        max_length=32,
        choices=RELATIONSHIP_CHOICES,
        default=RELATIONSHIP_BLOGROLL,
    )
    metadata = models.JSONField(default=dict)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["identity", "target_url", "relationship"],
                name="game_unique_neighbor_link",
            )
        ]
        ordering = ["target_url"]

    def __str__(self) -> str:
        return f"{self.identity_id}->{self.target_url}"


class GardenVisit(models.Model):
    """Unique, rate-limited visits from one gardener to another."""

    SOURCE_NEIGHBOR_GROVE = "neighbor_grove"
    SOURCE_SHARED_LINK = "shared_link"

    SOURCE_CHOICES = [
        (SOURCE_NEIGHBOR_GROVE, "Neighbor Grove"),
        (SOURCE_SHARED_LINK, "Shared Link"),
    ]

    host = models.ForeignKey(
        "plants.UserIdentity",
        on_delete=models.CASCADE,
        related_name="hosted_garden_visits",
    )
    visitor = models.ForeignKey(
        "plants.UserIdentity",
        on_delete=models.CASCADE,
        related_name="garden_visits",
    )
    visited_on = models.DateField()
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_NEIGHBOR_GROVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["host", "visitor", "visited_on"],
                name="game_unique_daily_garden_visit",
            )
        ]
        ordering = ["-visited_on", "-created_at"]

    def __str__(self) -> str:
        return f"{self.visitor_id}->{self.host_id}@{self.visited_on}"


class GameProfile(models.Model):
    """Extended profile for the game layer, linked to the existing gardn UserIdentity."""

    BODY_STYLE_FEMININE = "feminine"
    BODY_STYLE_ANDROGYNOUS = "androgynous"
    BODY_STYLE_MASCULINE = "masculine"

    BODY_STYLE_CHOICES = [
        (BODY_STYLE_FEMININE, "Feminine"),
        (BODY_STYLE_ANDROGYNOUS, "Androgynous"),
        (BODY_STYLE_MASCULINE, "Masculine"),
    ]

    GATE_OPEN = "open"
    GATE_CLOSED = "closed"

    GATE_STATE_CHOICES = [
        (GATE_OPEN, "Open"),
        (GATE_CLOSED, "Closed"),
    ]

    identity = models.OneToOneField(
        "plants.UserIdentity",
        on_delete=models.CASCADE,
        related_name="game_profile",
    )
    display_name = models.CharField(max_length=64, blank=True)

    # Player position (persisted between sessions)
    map_id = models.CharField(max_length=64, default="overworld")
    tile_x = models.IntegerField(default=10)
    tile_y = models.IntegerField(default=10)

    # Onboarding state
    tutorial_step = models.IntegerField(default=0)
    # 0 = not started, 1-N = tutorial steps, 999 = complete
    has_website = models.BooleanField(default=False)
    neocities_username = models.CharField(max_length=128, blank=True)
    appearance_configured = models.BooleanField(default=False)
    body_style = models.CharField(
        max_length=32,
        choices=BODY_STYLE_CHOICES,
        default=BODY_STYLE_ANDROGYNOUS,
    )
    skin_tone = models.CharField(max_length=32, default="olive")
    outfit_key = models.CharField(max_length=32, default="starter")

    # Game progression
    links_harvested = models.IntegerField(default=0)
    seeds_planted = models.IntegerField(default=0)
    garden_name = models.CharField(max_length=80, blank=True)
    gate_state = models.CharField(
        max_length=16,
        choices=GATE_STATE_CHOICES,
        default=GATE_OPEN,
    )
    homestead_level = models.PositiveSmallIntegerField(default=1)
    path_style = models.CharField(max_length=32, default="stone")
    fence_style = models.CharField(max_length=32, default="split_rail")
    read_later_tag = models.CharField(max_length=64, default="read-later")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"GameProfile({self.identity})"


class GardenPlot(models.Model):
    """A tile in the player's personal garden. Links grow here as plants."""

    profile = models.ForeignKey(
        GameProfile, on_delete=models.CASCADE, related_name="garden_plots"
    )
    slot_x = models.IntegerField()  # position in garden grid (0-7)
    slot_y = models.IntegerField()  # position in garden grid (0-7)

    # What's growing here
    verified_activity = models.ForeignKey(
        "game.VerifiedActivity",
        on_delete=models.SET_NULL,
        related_name="garden_plots",
        null=True,
        blank=True,
    )
    link_url = models.URLField(max_length=2048, blank=True)
    link_title = models.CharField(max_length=500, blank=True)
    plant_type = models.CharField(max_length=64, blank=True)  # maps to LPC crop sprite
    growth_stage = models.IntegerField(default=0)  # 0-4 (LPC crops have 5 frames)
    planted_at = models.DateTimeField(null=True, blank=True)
    last_watered = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("profile", "slot_x", "slot_y")

    def __str__(self) -> str:
        return f"Plot({self.profile.identity}, {self.slot_x},{self.slot_y})"


class GardenDecoration(models.Model):
    """Anchored decor placed around the player's homestead."""

    SLOT_NORTH_WEST = "north_west"
    SLOT_NORTH_EAST = "north_east"
    SLOT_SOUTH_WEST = "south_west"
    SLOT_SOUTH_EAST = "south_east"
    SLOT_SIGNPOST = "signpost"

    SLOT_CHOICES = [
        (SLOT_NORTH_WEST, "Northwest"),
        (SLOT_NORTH_EAST, "Northeast"),
        (SLOT_SOUTH_WEST, "Southwest"),
        (SLOT_SOUTH_EAST, "Southeast"),
        (SLOT_SIGNPOST, "Signpost"),
    ]

    profile = models.ForeignKey(
        GameProfile,
        on_delete=models.CASCADE,
        related_name="decorations",
    )
    slot_key = models.CharField(max_length=32, choices=SLOT_CHOICES)
    decor_key = models.CharField(max_length=32)
    variant_key = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "slot_key"],
                name="game_unique_garden_decoration_slot",
            )
        ]
        ordering = ["slot_key"]

    def __str__(self) -> str:
        return f"{self.profile.identity}:{self.slot_key}:{self.decor_key}"


class Quest(models.Model):
    """Quest definitions. Seed these via a data migration."""

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=128)
    description = models.TextField()
    # Trigger type: 'tutorial', 'indieweb', 'community', 'seasonal'
    category = models.CharField(max_length=32)
    order = models.IntegerField(default=0)
    # e.g. {"requires_website": true, "min_links": 3, "quest_slug": "some-prerequisite"}
    requirements = models.JSONField(default=dict)
    # e.g. {"xp": 50, "plant_type": "tomato", "unlock_area": "library"}
    rewards = models.JSONField(default=dict)
    npc_id = models.CharField(max_length=64, blank=True)  # which NPC gives this quest

    def __str__(self) -> str:
        return self.title


class QuestProgress(models.Model):
    """Tracks which quests a player has started/completed."""

    profile = models.ForeignKey(
        GameProfile, on_delete=models.CASCADE, related_name="quest_progress"
    )
    quest = models.ForeignKey(Quest, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=16,
        choices=[
            ("active", "Active"),
            ("complete", "Complete"),
            ("abandoned", "Abandoned"),
        ],
        default="active",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    # Flexible progress tracking (e.g. {"links_found": 2, "target": 3})
    progress_data = models.JSONField(default=dict)

    class Meta:
        unique_together = ("profile", "quest")


class GrovePresence(models.Model):
    """Tracks near-real-time grove presence for short-poll social features."""

    identity = models.OneToOneField(
        "plants.UserIdentity",
        on_delete=models.CASCADE,
        related_name="grove_presence",
    )
    current_map = models.CharField(max_length=32, default="neighbors")
    last_seen_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.identity}:{self.current_map}"


class GroveMessage(models.Model):
    """Public messages posted in the Neighbor Grove."""

    identity = models.ForeignKey(
        "plants.UserIdentity",
        on_delete=models.CASCADE,
        related_name="grove_messages",
    )
    content = models.CharField(max_length=280)
    is_moderated = models.BooleanField(default=False)
    moderated_reason = models.CharField(max_length=120, blank=True)
    moderated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.identity}: {self.content[:32]}"
