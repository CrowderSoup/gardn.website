from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass


SVG_RENDER_VERSION = "v7"


@dataclass(frozen=True)
class PlantTraits:
    palette: tuple[str, str, str, str]
    trunk_style: int
    trunk_curve: int
    trunk_width: int
    canopy_style: int
    leaf_count: int
    leaf_size: int
    flower_style: int
    bloom_count: int
    pot_style: int
    pot_colorway: int
    bg_style: int
    aura_style: int
    growth_feature: int
    motion_style: int
    motion_duration_s: int
    harvest_count: int
    pick_count: int


# dark bark, natural leaf, restrained tech accent, soft haze
PALETTES = [
    ("#3a2a1f", "#547a4c", "#6d90ad", "#f6f2e9"),
    ("#423126", "#62855b", "#8f7a62", "#f5efe4"),
    ("#352d22", "#4e7452", "#7a8ea4", "#f1eee7"),
    ("#453428", "#6f885f", "#9d765d", "#f8f3eb"),
    ("#3d3026", "#5b7f4f", "#74899e", "#f4f0e8"),
    ("#2f281f", "#688a61", "#8a806b", "#f2efe6"),
]


def _biased_pot_style(seed_value: int, harvest_count: int, pick_count: int) -> int:
    activity = harvest_count + pick_count
    if activity < 3:
        pool = (0, 1, 2, 3)
    elif activity < 8:
        pool = (1, 2, 3, 4, 5)
    elif activity < 15:
        pool = (2, 3, 4, 5, 6)
    else:
        pool = (3, 4, 5, 6, 7)
    return pool[seed_value % len(pool)]


def traits_from_seed(seed: str, harvest_count: int = 0, pick_count: int = 0) -> PlantTraits:
    nums = [int(seed[i: i + 2], 16) for i in range(0, 32, 2)]

    if harvest_count == 0:
        growth_feature = 0
    elif harvest_count < 5:
        growth_feature = (nums[7] % 2) + 1
    elif harvest_count < 10:
        growth_feature = (nums[7] % 4) + 1
    else:
        growth_feature = (nums[7] % 5) + 1

    if harvest_count < 4:
        bloom_count = 1
    elif harvest_count < 11:
        bloom_count = 2
    else:
        bloom_count = 3

    return PlantTraits(
        palette=PALETTES[nums[0] % len(PALETTES)],
        trunk_style=nums[1] % 3,
        trunk_curve=(nums[2] % 80) - 40,
        trunk_width=6 + (nums[3] % 4),
        canopy_style=nums[4] % 4,
        leaf_count=8 + (nums[5] % 8),
        leaf_size=nums[6] % 3,
        flower_style=nums[8] % 5,
        bloom_count=bloom_count,
        pot_style=_biased_pot_style(nums[9], harvest_count, pick_count),
        pot_colorway=nums[14] % 4,
        bg_style=nums[10] % 4,
        aura_style=nums[11] % 3,
        growth_feature=growth_feature,
        motion_style=nums[12] % 3,
        motion_duration_s=6 + (nums[13] % 5),
        harvest_count=harvest_count,
        pick_count=pick_count,
    )


def _defs(traits: PlantTraits) -> str:
    _, leaf, accent, light = traits.palette
    return (
        "<defs>"
        f'<linearGradient id="leaf-fill" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0%" stop-color="{leaf}"/>'
        f'<stop offset="100%" stop-color="{accent}" stop-opacity="0.45"/>'
        "</linearGradient>"
        f'<linearGradient id="pot-fill" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0%" stop-color="{light}" stop-opacity="0.9"/>'
        f'<stop offset="100%" stop-color="{accent}" stop-opacity="0.42"/>'
        "</linearGradient>"
        f'<radialGradient id="aura-fill" cx="50%" cy="34%" r="58%">'
        f'<stop offset="0%" stop-color="{leaf}" stop-opacity="0.12"/>'
        f'<stop offset="62%" stop-color="{accent}" stop-opacity="0.06"/>'
        '<stop offset="100%" stop-color="#ffffff" stop-opacity="0"/>'
        "</radialGradient>"
        f'<filter id="leaf-glow" x="-40%" y="-40%" width="180%" height="180%">'
        f'<feDropShadow dx="0" dy="0" stdDeviation="1.1" flood-color="{accent}" flood-opacity="0.34"/>'
        f'<feDropShadow dx="0" dy="0" stdDeviation="1.8" flood-color="{leaf}" flood-opacity="0.16"/>'
        "</filter>"
        f'<filter id="soft-blur" x="-40%" y="-40%" width="180%" height="180%">'
        '<feGaussianBlur stdDeviation="1.1"/>'
        "</filter>"
        "</defs>"
    )


def _background(traits: PlantTraits) -> str:
    _, leaf, accent, light = traits.palette
    if traits.bg_style == 0:
        return (
            f'<rect width="300" height="240" fill="{light}"/>'
            f'<path d="M0 200 Q 150 184 300 200" stroke="{leaf}" stroke-width="1.2" opacity="0.14" fill="none"/>'
        )
    if traits.bg_style == 1:
        return (
            f'<rect width="300" height="240" fill="{light}"/>'
            f'<rect x="0" y="0" width="300" height="240" fill="url(#aura-fill)"/>'
            f'<path d="M36 214 L36 146 M64 214 L64 154 M92 214 L92 142" stroke="{accent}" opacity="0.16"/>'
            f'<circle cx="36" cy="144" r="1.3" fill="{accent}" opacity="0.28"/>'
            f'<circle cx="92" cy="140" r="1.3" fill="{accent}" opacity="0.28"/>'
        )
    if traits.bg_style == 2:
        return (
            f'<rect width="300" height="240" fill="{light}"/>'
            f'<circle cx="62" cy="56" r="22" fill="{accent}" opacity="0.08" filter="url(#soft-blur)"/>'
            f'<circle cx="242" cy="50" r="15" fill="{leaf}" opacity="0.11" filter="url(#soft-blur)"/>'
            f'<path d="M0 220 Q 60 195 120 220 T 240 220 T 300 220" fill="none" stroke="{leaf}" stroke-opacity="0.1" stroke-width="1.3"/>'
        )
    return (
        f'<rect width="300" height="240" fill="{light}"/>'
        f'<path d="M0 206 Q 150 178 300 206" fill="none" stroke="{accent}" stroke-opacity="0.1" stroke-width="1.2"/>'
        f'<path d="M0 218 Q 150 190 300 218" fill="none" stroke="{leaf}" stroke-opacity="0.1" stroke-width="1"/>'
        f'<rect x="0" y="0" width="300" height="240" fill="url(#aura-fill)" opacity="0.2"/>'
    )


def _aura(traits: PlantTraits, motion_enabled: bool) -> str:
    if traits.aura_style == 0:
        return ""
    _, leaf, accent, _ = traits.palette
    dur = max(4, traits.motion_duration_s - 2)
    if traits.aura_style == 1:
        if not motion_enabled:
            return f'<ellipse cx="150" cy="108" rx="58" ry="50" fill="{accent}" opacity="0.08" filter="url(#soft-blur)"/>'
        return (
            f'<ellipse cx="150" cy="108" rx="58" ry="50" fill="{accent}" opacity="0.08" filter="url(#soft-blur)">'
            f'<animate attributeName="opacity" values="0.05;0.13;0.05" dur="{dur}s" repeatCount="indefinite"/>'
            "</ellipse>"
        )
    if not motion_enabled:
        return (
            '<g>'
            '<ellipse cx="150" cy="104" rx="66" ry="46" fill="url(#aura-fill)" filter="url(#soft-blur)" opacity="0.3"/>'
            f'<ellipse cx="150" cy="104" rx="42" ry="30" fill="{leaf}" opacity="0.08"/>'
            '</g>'
        )
    return (
        '<g>'
        '<ellipse cx="150" cy="104" rx="66" ry="46" fill="url(#aura-fill)" filter="url(#soft-blur)">'
        f'<animate attributeName="opacity" values="0.22;0.4;0.22" dur="{dur}s" repeatCount="indefinite"/>'
        "</ellipse>"
        f'<ellipse cx="150" cy="104" rx="42" ry="30" fill="{leaf}" opacity="0.08">'
        f'<animate attributeName="opacity" values="0.05;0.12;0.05" dur="{dur}s" repeatCount="indefinite"/>'
        "</ellipse>"
        '</g>'
    )


def _trunk(traits: PlantTraits) -> str:
    bark = traits.palette[0]
    c = traits.trunk_curve
    width = traits.trunk_width
    if traits.trunk_style == 0:
        d = f'M150 184 C {150 + c} 170 {150 - c} 122 148 84'
    elif traits.trunk_style == 1:
        d = f'M150 184 C {150 + c} 172 {150 + c // 2} 130 {148 - c // 2} 106 C {146 - c // 2} 92 150 88 152 82'
    else:
        d = f'M150 184 Q {150 + c} 152 {140 + c // 3} 130 Q {130 + c // 2} 104 152 82'
    return (
        f'<path d="{d}" stroke="{bark}" stroke-width="{width}" fill="none" stroke-linecap="round"/>'
        f'<path d="{d}" stroke="{traits.palette[2]}" stroke-width="1" fill="none" opacity="0.16"/>'
    )


def _leaf_blob(cx: int, cy: int, rx: int, ry: int, traits: PlantTraits, idx: int) -> str:
    leaf_fill = "url(#leaf-fill)"
    rotation = -18 + (idx % 5) * 9
    highlight = traits.palette[3]
    return (
        f'<g transform="rotate({rotation} {cx} {cy})">'
        f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="{leaf_fill}" filter="url(#leaf-glow)" opacity="0.86"/>'
        f'<ellipse cx="{cx - 2}" cy="{cy - 2}" rx="{max(1, rx - 4)}" ry="{max(1, ry - 4)}" fill="{highlight}" opacity="0.07"/>'
        "</g>"
    )


def _canopy(traits: PlantTraits, seed: str) -> str:
    nums = [int(seed[i: i + 2], 16) for i in range(0, 32, 2)]
    size_mult = [0.85, 1.0, 1.18][traits.leaf_size]
    center_x = 148
    center_y = 103
    radius = [26, 31, 28, 33][traits.canopy_style]
    leaves: list[str] = []

    for i in range(traits.leaf_count):
        angle = (360 / traits.leaf_count) * i + (nums[i % 8] % 18)
        radians = math.radians(angle)
        distance = radius + ((i * 3 + nums[(i + 3) % 8]) % 10) - 4
        cx = center_x + int(math.cos(radians) * distance)
        cy = center_y + int(math.sin(radians) * (distance * 0.74))
        rx = int((10 + (nums[(i + 5) % 8] % 6)) * size_mult)
        ry = int((7 + (nums[(i + 7) % 8] % 5)) * size_mult)
        leaves.append(_leaf_blob(cx, cy, rx, ry, traits, i))

    trunk_tip = (
        f'<path d="M148 92 Q 140 86 134 80" stroke="{traits.palette[0]}" stroke-width="2.8" fill="none" stroke-linecap="round" opacity="0.85"/>'
        f'<path d="M149 90 Q 159 82 168 82" stroke="{traits.palette[0]}" stroke-width="2.4" fill="none" stroke-linecap="round" opacity="0.82"/>'
    )
    return trunk_tip + "".join(leaves)


def _flower(cx: int, cy: int, traits: PlantTraits, idx: int, motion_enabled: bool) -> str:
    accent = traits.palette[2]
    leaf = traits.palette[1]
    light = traits.palette[3]
    style = (traits.flower_style + idx) % 5
    if style == 0:
        bloom = f'<circle cx="{cx}" cy="{cy}" r="5" fill="{accent}" filter="url(#leaf-glow)"/>'
    elif style == 1:
        bloom = f'<rect x="{cx - 4}" y="{cy - 4}" width="8" height="8" rx="2" fill="{accent}" filter="url(#leaf-glow)"/>'
    elif style == 2:
        bloom = f'<polygon points="{cx},{cy - 6} {cx + 5},{cy + 4} {cx - 5},{cy + 4}" fill="{accent}" filter="url(#leaf-glow)"/>'
    elif style == 3:
        bloom = (
            f'<ellipse cx="{cx - 3}" cy="{cy}" rx="3" ry="5" fill="{accent}"/>'
            f'<ellipse cx="{cx + 3}" cy="{cy}" rx="3" ry="5" fill="{accent}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="2" fill="{light}"/>'
        )
    else:
        bloom = f'<circle cx="{cx}" cy="{cy}" r="4" fill="{leaf}"/><circle cx="{cx}" cy="{cy}" r="2" fill="{light}"/>'

    if not motion_enabled:
        return f"<g>{bloom}</g>"
    pulse_dur = max(4, traits.motion_duration_s)
    return (
        f'<g>'
        f'{bloom}'
        f'<animateTransform attributeName="transform" type="scale" values="1 1;1.08 1.08;1 1" dur="{pulse_dur}s" repeatCount="indefinite" additive="sum"/>'
        f'<animateTransform attributeName="transform" type="translate" values="0 0;0 -1;0 0" dur="{pulse_dur}s" repeatCount="indefinite" additive="sum"/>'
        '</g>'
    )


def _flowers(traits: PlantTraits, seed: str, motion_enabled: bool) -> str:
    nums = [int(seed[i: i + 2], 16) for i in range(0, 32, 2)]
    positions = [
        (132, 86),
        (168, 88),
        (148, 76),
        (158, 98),
        (138, 98),
    ]
    blooms = []
    for i in range(traits.bloom_count):
        base_x, base_y = positions[(nums[i] + i) % len(positions)]
        blooms.append(_flower(base_x, base_y, traits, i, motion_enabled))
    return "".join(blooms)


def _pot(traits: PlantTraits) -> str:
    bark, _, accent, light = traits.palette
    pot_palettes = [
        ("#a9683f", "#7c4a2c", "#d8b49a"),  # terracotta
        ("#486f8f", "#2f4f69", "#b8cfdf"),  # ceramic blue
        ("#56725f", "#374e41", "#c3d2c8"),  # moss glaze
        ("#5d4d66", "#3f3346", "#d0c0d8"),  # plum glaze
    ]
    body, rim, stripe = pot_palettes[traits.pot_colorway]
    if traits.pot_style == 0:
        return (
            '<g>'
            f'<rect x="102" y="184" width="96" height="48" rx="8" fill="{body}"/>'
            f'<rect x="96" y="178" width="108" height="10" rx="5" fill="{rim}"/>'
            f'<path d="M108 198 H192" stroke="{stripe}" stroke-opacity="0.35"/>'
            '</g>'
        )
    if traits.pot_style == 1:
        return (
            '<g>'
            f'<path d="M98 180 H202 L192 232 H108 Z" fill="{body}"/>'
            f'<path d="M98 180 H202" stroke="{stripe}" stroke-width="2" opacity="0.7"/>'
            f'<path d="M112 208 H188" stroke="{rim}" stroke-width="1.3" opacity="0.45"/>'
            '</g>'
        )
    if traits.pot_style == 2:
        return (
            '<g>'
            f'<ellipse cx="150" cy="186" rx="54" ry="10" fill="{bark}"/>'
            f'<rect x="102" y="186" width="96" height="46" rx="12" fill="{body}"/>'
            f'<path d="M108 202 H192" stroke="{stripe}" stroke-width="1.5" opacity="0.5"/>'
            '</g>'
        )
    if traits.pot_style == 3:
        return (
            '<g>'
            f'<rect x="108" y="182" width="84" height="50" rx="5" fill="{body}"/>'
            f'<path d="M108 194 H192 M108 206 H192 M108 218 H192" stroke="{stripe}" stroke-opacity="0.4"/>'
            f'<rect x="104" y="178" width="92" height="9" rx="4" fill="{rim}"/>'
            '</g>'
        )
    if traits.pot_style == 4:
        return (
            '<g>'
            f'<ellipse cx="150" cy="184" rx="52" ry="9" fill="{rim}"/>'
            f'<path d="M98 184 Q 150 198 202 184 L194 232 Q 150 226 106 232 Z" fill="{body}"/>'
            f'<path d="M116 204 Q 150 214 184 204" stroke="{stripe}" stroke-width="1.4" opacity="0.45" fill="none"/>'
            '</g>'
        )
    if traits.pot_style == 5:
        return (
            '<g>'
            f'<rect x="104" y="184" width="92" height="48" rx="10" fill="{body}"/>'
            f'<rect x="98" y="178" width="104" height="10" rx="5" fill="{rim}"/>'
            f'<circle cx="118" cy="206" r="4" fill="{stripe}" opacity="0.45"/>'
            f'<circle cx="150" cy="206" r="4" fill="{stripe}" opacity="0.45"/>'
            f'<circle cx="182" cy="206" r="4" fill="{stripe}" opacity="0.45"/>'
            '</g>'
        )
    if traits.pot_style == 6:
        return (
            '<g>'
            f'<path d="M110 182 H190 L182 232 H118 Z" fill="{body}"/>'
            f'<path d="M106 178 H194" stroke="{rim}" stroke-width="5" stroke-linecap="round"/>'
            f'<path d="M124 198 H176 M126 210 H174 M128 222 H172" stroke="{stripe}" stroke-opacity="0.42"/>'
            '</g>'
        )
    return (
        '<g>'
        f'<ellipse cx="150" cy="184" rx="50" ry="8" fill="{rim}"/>'
        f'<rect x="106" y="184" width="88" height="50" rx="16" fill="{body}"/>'
        f'<path d="M116 200 C 132 194, 168 194, 184 200" stroke="{stripe}" stroke-width="1.4" fill="none" opacity="0.5"/>'
        f'<path d="M118 214 C 134 208, 166 208, 182 214" stroke="{stripe}" stroke-width="1.2" fill="none" opacity="0.45"/>'
        '</g>'
    )


def _growth_feature(traits: PlantTraits, seed: str, motion_enabled: bool) -> str:
    if traits.growth_feature == 0:
        return ""

    bark, leaf, accent, _ = traits.palette
    nums = [int(seed[i: i + 2], 16) for i in range(0, 32, 2)]

    if traits.growth_feature == 1:
        vines = []
        for i in range(2 + (nums[10] % 2)):
            sy = 168 - i * 18
            direction = 1 if i % 2 == 0 else -1
            ex = 150 + direction * (24 + nums[(11 + i) % 16] % 14)
            ey = sy - 22
            vines.append(
                f'<path d="M150 {sy} Q {150 + direction * 10} {sy - 6} {ex} {ey}" stroke="{leaf}" stroke-width="1.4" fill="none" opacity="0.7"/>'
            )
        return "".join(vines)

    if traits.growth_feature == 2:
        berries = []
        for i in range(5 + (nums[9] % 3)):
            direction = -1 if i % 2 == 0 else 1
            bx = 150 + direction * (18 + (nums[i % 8] % 14))
            by = 92 + (i * 16) % 74
            berries.append(f'<circle cx="{bx}" cy="{by}" r="3.4" fill="{accent}" filter="url(#leaf-glow)" opacity="0.76"/>')
        return "".join(berries)

    if traits.growth_feature == 3:
        return (
            f'<path d="M66 188 Q 74 156 64 138" stroke="{bark}" stroke-width="4" fill="none"/>'
            f'<ellipse cx="62" cy="132" rx="14" ry="11" fill="{leaf}" opacity="0.72" filter="url(#leaf-glow)"/>'
            f'<rect x="42" y="188" width="36" height="20" rx="4" fill="{accent}" opacity="0.75"/>'
        )

    if traits.growth_feature == 4:
        stars = []
        positions = [(36, 44), (266, 52), (24, 138), (274, 162), (78, 34), (220, 28)]
        for i, (x, y) in enumerate(positions[:4 + (nums[10] % 3)]):
            if motion_enabled:
                stars.append(
                    f'<g><circle cx="{x}" cy="{y}" r="2.2" fill="{accent}" opacity="0.45"/>'
                    f'<animate attributeName="opacity" values="0.18;0.55;0.18" dur="{5 + (i % 3)}s" repeatCount="indefinite"/>'
                    '</g>'
                )
            else:
                stars.append(f'<circle cx="{x}" cy="{y}" r="2.2" fill="{accent}" opacity="0.3"/>')
        return "".join(stars)

    moss = []
    for i in range(5):
        mx = 115 + i * 14
        moss.append(f'<ellipse cx="{mx}" cy="233" rx="7" ry="4" fill="{leaf}" opacity="0.45"/>')
    return "".join(moss)


def _motion_open(traits: PlantTraits, motion_enabled: bool) -> str:
    dur = traits.motion_duration_s
    if traits.motion_style == 0:
        values = "-0.8 150 184;0.8 150 184;-0.8 150 184"
    elif traits.motion_style == 1:
        values = "-0.6 150 184;0.45 150 184;-0.6 150 184"
    else:
        values = "-1.0 150 184;1.0 150 184;-1.0 150 184"
    if not motion_enabled:
        return '<g id="plant-motion">'
    return (
        '<g id="plant-motion">'
        f'<animateTransform attributeName="transform" type="rotate" values="{values}" dur="{dur}s" repeatCount="indefinite"/>'
    )


def _motion_close() -> str:
    return "</g>"


def _tech_flares(traits: PlantTraits, seed: str, motion_enabled: bool) -> str:
    _, leaf, accent, _ = traits.palette
    nums = [int(seed[i: i + 2], 16) for i in range(0, 32, 2)]
    particles = []
    for i in range(4):
        x = 95 + (nums[i] % 110)
        y = 74 + (nums[i + 4] % 72)
        color = accent if i % 2 == 0 else leaf
        dur = 5 + (nums[i + 8] % 4)
        dy = 8 + (nums[i + 12] % 6)
        if motion_enabled:
            particles.append(
                f'<circle cx="{x}" cy="{y}" r="1.8" fill="{color}" opacity="0.22">'
                f'<animate attributeName="cy" values="{y};{y - dy};{y}" dur="{dur}s" repeatCount="indefinite"/>'
                f'<animate attributeName="opacity" values="0.06;0.22;0.06" dur="{dur}s" repeatCount="indefinite"/>'
                '</circle>'
            )
        else:
            particles.append(f'<circle cx="{x}" cy="{y}" r="1.7" fill="{color}" opacity="0.12"/>')
    return "".join(particles)


def generate_svg(
    canonical_me_url: str,
    harvest_urls: list[str] | None = None,
    motion_enabled: bool = False,
    pick_count: int = 0,
) -> str:
    base_seed = hashlib.sha256(canonical_me_url.encode("utf-8")).hexdigest()
    if harvest_urls:
        harvest_input = ",".join(sorted(harvest_urls))
        growth_seed = hashlib.sha256(harvest_input.encode("utf-8")).hexdigest()
        combined = hashlib.sha256((base_seed + growth_seed).encode("utf-8")).hexdigest()
    else:
        combined = base_seed

    harvest_count = len(harvest_urls) if harvest_urls else 0
    traits = traits_from_seed(combined, harvest_count, pick_count)

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 240" role="img" aria-label="Garden plant">\n'
        f'  <!-- render:{SVG_RENDER_VERSION};motion:{int(motion_enabled)} -->\n'
        f'  {_defs(traits)}\n'
        f'  {_background(traits)}\n'
        f'  {_aura(traits, motion_enabled)}\n'
        f'  {_tech_flares(traits, combined, motion_enabled)}\n'
        f'  {_motion_open(traits, motion_enabled)}\n'
        f'    {_growth_feature(traits, combined, motion_enabled)}\n'
        f'    {_trunk(traits)}\n'
        f'    {_canopy(traits, combined)}\n'
        f'    {_flowers(traits, combined, motion_enabled)}\n'
        f'    {_pot(traits)}\n'
        f'  {_motion_close()}\n'
        '</svg>'
    )
    return svg
