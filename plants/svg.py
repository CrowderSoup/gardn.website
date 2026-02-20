from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PlantTraits:
    palette: tuple[str, str, str, str]
    stem_curve: int       # -30 to +30
    stem_style: int       # 0=simple, 1=S-curve, 2=lean
    leaf_count: int       # 3-9
    leaf_shape: int       # 0-4
    leaf_size: int        # 0-2 (small/medium/large)
    flower_style: int     # 0-7
    pot_style: int        # 0-3
    bg_style: int         # 0-3
    harvest_count: int
    growth_feature: int   # 0=none,1=tendrils,2=berries,3=secondary,4=sparkles,5=moss


PALETTES = [
    # greens
    ("#1b4332", "#2d6a4f", "#74c69d", "#e9f5db"),  # 0 forest
    ("#386641", "#6a994e", "#a7c957", "#f2e8cf"),  # 1 meadow
    ("#344e41", "#3a5a40", "#588157", "#dad7cd"),  # 2 sage
    ("#283618", "#606c38", "#dda15e", "#fefae0"),  # 3 earthy
    # teal/ocean
    ("#004d40", "#00796b", "#4db6ac", "#e0f2f1"),  # 4 teal
    ("#1a3b5c", "#2e6e9e", "#7ab8d8", "#e0f2fc"),  # 5 ocean
    # desert/warm
    ("#6d4c41", "#a1887f", "#d7ccc8", "#fbe9e7"),  # 6 terracotta
    ("#5c3a00", "#a66b00", "#e8c84a", "#fff9e0"),  # 7 golden
    # moody/dramatic
    ("#1a1a2e", "#16213e", "#5a6fa8", "#e8ecf8"),  # 8 midnight
    ("#2d1b69", "#553d9e", "#9b77d4", "#f0e8ff"),  # 9 amethyst
    # floral
    ("#3b1f2b", "#6b3d5e", "#c4788a", "#fce4ec"),  # 10 rose
    ("#4a1942", "#882b6c", "#d44fa0", "#ffe4f0"),  # 11 fuchsia
    # fire/autumn
    ("#7c3902", "#c05c02", "#f0a040", "#fff3c4"),  # 12 autumn
    ("#5d1800", "#a32c00", "#e85c00", "#fff0e0"),  # 13 ember
    # cool/serene
    ("#1a4a3a", "#2e8a6a", "#74c9a8", "#e8f8f2"),  # 14 seafoam
    ("#2c3e50", "#5d6d7e", "#aab7b8", "#f2f3f4"),  # 15 slate
]


def traits_from_seed(seed: str, harvest_count: int = 0) -> PlantTraits:
    nums = [int(seed[i: i + 2], 16) for i in range(0, 32, 2)]
    palette = PALETTES[nums[0] % len(PALETTES)]

    if harvest_count == 0:
        growth_feature = 0
    elif harvest_count < 5:
        growth_feature = (nums[7] % 2) + 1  # 1 or 2
    elif harvest_count < 10:
        growth_feature = (nums[7] % 4) + 1  # 1-4
    else:
        growth_feature = (nums[7] % 5) + 1  # 1-5

    return PlantTraits(
        palette=palette,
        stem_curve=(nums[1] % 60) - 30,
        stem_style=nums[2] % 3,
        leaf_count=3 + (nums[3] % 7),
        leaf_shape=nums[4] % 5,
        leaf_size=nums[5] % 3,
        flower_style=nums[6] % 8,
        pot_style=nums[8] % 4,
        bg_style=nums[9] % 4,
        harvest_count=harvest_count,
        growth_feature=growth_feature,
    )


def _background(traits: PlantTraits) -> str:
    dark, leaf, accent, light = traits.palette
    if traits.bg_style == 0:
        return f'<rect width="300" height="240" fill="{light}"/>'
    if traits.bg_style == 1:
        return (
            f'<defs><radialGradient id="bg" cx="50%" cy="40%" r="60%">'
            f'<stop offset="0%" stop-color="{light}"/>'
            f'<stop offset="100%" stop-color="{accent}" stop-opacity="0.4"/>'
            f'</radialGradient></defs>'
            f'<rect width="300" height="240" fill="url(#bg)"/>'
        )
    if traits.bg_style == 2:
        return (
            f'<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="{light}"/>'
            f'<stop offset="100%" stop-color="{accent}" stop-opacity="0.3"/>'
            f'</linearGradient></defs>'
            f'<rect width="300" height="240" fill="url(#bg)"/>'
        )
    # bg_style == 3: ambient dot pattern
    dots = []
    positions = [(30, 20), (270, 30), (50, 200), (260, 190), (150, 15), (80, 110), (230, 115)]
    for i, (x, y) in enumerate(positions):
        r = 3 + (i % 3)
        dots.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{accent}" opacity="0.25"/>')
    return f'<rect width="300" height="240" fill="{light}"/>{"".join(dots)}'


def _stem(traits: PlantTraits) -> str:
    dark = traits.palette[0]
    c = traits.stem_curve
    if traits.stem_style == 0:
        return f'<path d="M150 184 Q {150 + c} 130 150 80" stroke="{dark}" stroke-width="6" fill="none" stroke-linecap="round"/>'
    if traits.stem_style == 1:
        return f'<path d="M150 184 C {150 + c} 160 {150 - c} 120 150 80" stroke="{dark}" stroke-width="6" fill="none" stroke-linecap="round"/>'
    # stem_style == 2: lean
    tip_x = 150 + c // 2
    return f'<path d="M150 184 Q {150 + c} 140 {tip_x} 80" stroke="{dark}" stroke-width="6" fill="none" stroke-linecap="round"/>'


def _leaf_path(idx: int, traits: PlantTraits) -> str:
    leaf_color = traits.palette[1]
    size_mult = [0.8, 1.0, 1.3][traits.leaf_size]
    y = 170 - idx * 15
    direction = -1 if idx % 2 == 0 else 1
    base_offset = int((18 + idx) * size_mult)
    lx = 150 + direction * base_offset

    if traits.leaf_shape == 0:
        path = (
            f'M 150 {y} Q {lx} {y - 8} {lx} {y - 18} '
            f'Q {150 + direction * 6} {y - 10} 150 {y}'
        )
    elif traits.leaf_shape == 1:
        # Pointed/lance
        tip_x = 150 + direction * int(22 * size_mult)
        path = (
            f'M 150 {y} Q {tip_x} {y - 5} {tip_x + direction * 5} {y - 22} '
            f'Q {tip_x} {y - 8} 150 {y}'
        )
    elif traits.leaf_shape == 2:
        # Round/fat
        fat = int(26 * size_mult)
        path = (
            f'M 150 {y} C {150 + direction * fat} {y + 4} '
            f'{150 + direction * fat} {y - 22} 150 {y - 20} '
            f'C {150 + direction * 8} {y - 12} 150 {y - 4} 150 {y}'
        )
    elif traits.leaf_shape == 3:
        # Compound two-lobed
        small_lx = 150 + direction * int(10 * size_mult)
        big_lx = 150 + direction * int(20 * size_mult)
        path = (
            f'M 150 {y} Q {small_lx} {y - 4} {small_lx} {y - 12} '
            f'Q {150 + direction * 4} {y - 6} 150 {y} '
            f'Q {big_lx} {y - 8} {big_lx} {y - 20} '
            f'Q {150 + direction * 8} {y - 12} 150 {y}'
        )
    else:
        # Narrow/grass
        w = direction * int(12 * size_mult)
        path = (
            f'M 150 {y} L {150 + w} {y - 3} L {150 + w + direction * 2} {y - 22} '
            f'L 150 {y - 19} Z'
        )

    return f'<path d="{path}" fill="{leaf_color}" opacity="0.9"/>'


def _flower(traits: PlantTraits) -> str:
    _, leaf, accent, light = traits.palette
    c = traits.stem_curve
    cx = (150 + c // 2) if traits.stem_style == 2 else 150
    cy = 75

    if traits.flower_style == 0:
        return (
            f'<circle cx="{cx}" cy="{cy}" r="14" fill="{accent}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="6" fill="{light}"/>'
        )
    if traits.flower_style == 1:
        x0, y0 = cx - 10, cy - 11
        return (
            f'<rect x="{x0}" y="{y0}" width="20" height="20" rx="6" fill="{accent}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="5" fill="{leaf}"/>'
        )
    if traits.flower_style == 2:
        pts = f"{cx},{cy - 17} {cx + 12},{cy + 11} {cx - 12},{cy + 11}"
        return (
            f'<polygon points="{pts}" fill="{accent}"/>'
            f'<circle cx="{cx}" cy="{cy + 2}" r="5" fill="{light}"/>'
        )
    if traits.flower_style == 3:
        # 5-petal daisy
        petals = []
        for i in range(5):
            angle = math.radians(i * 72 - 90)
            px = cx + int(11 * math.cos(angle))
            py = cy + int(11 * math.sin(angle))
            petals.append(
                f'<ellipse cx="{px}" cy="{py}" rx="5" ry="8" '
                f'transform="rotate({i * 72 - 90} {px} {py})" fill="{accent}" opacity="0.9"/>'
            )
        return "".join(petals) + f'<circle cx="{cx}" cy="{cy}" r="6" fill="{light}"/>'
    if traits.flower_style == 4:
        # 8-point sunburst star
        outer, inner = 14, 6
        pts_list = []
        for i in range(16):
            r = outer if i % 2 == 0 else inner
            angle = math.radians(i * 22.5 - 90)
            pts_list.append(f"{cx + r * math.cos(angle):.1f},{cy + r * math.sin(angle):.1f}")
        return (
            f'<polygon points="{" ".join(pts_list)}" fill="{accent}"/>'
            f'<circle cx="{cx}" cy="{cy}" r="4" fill="{light}"/>'
        )
    if traits.flower_style == 5:
        # Tulip/bell
        return (
            f'<path d="M {cx - 10} {cy} C {cx - 12} {cy - 16} {cx + 12} {cy - 16} {cx + 10} {cy} '
            f'C {cx + 8} {cy + 8} {cx - 8} {cy + 8} {cx - 10} {cy} Z" fill="{accent}"/>'
            f'<path d="M {cx} {cy - 16} Q {cx + 6} {cy - 22} {cx + 4} {cy - 26}" stroke="{leaf}" stroke-width="2" fill="none"/>'
            f'<path d="M {cx} {cy - 16} Q {cx - 6} {cy - 22} {cx - 4} {cy - 26}" stroke="{leaf}" stroke-width="2" fill="none"/>'
        )
    if traits.flower_style == 6:
        # Cluster of small dots
        offsets = [(-8, -6), (0, -12), (8, -6), (-5, 2), (5, 2), (0, -2)]
        return "".join(
            f'<circle cx="{cx + dx}" cy="{cy + dy}" r="4" fill="{accent}" opacity="0.85"/>'
            for dx, dy in offsets
        )
    # flower_style == 7: spiral/abstract arcs
    return (
        f'<path d="M {cx} {cy} m -8 0 a 8 8 0 0 1 16 0 a 10 10 0 0 0 -20 0 a 12 12 0 0 1 24 0" '
        f'stroke="{accent}" stroke-width="2.5" fill="none" stroke-linecap="round"/>'
        f'<circle cx="{cx}" cy="{cy}" r="4" fill="{light}"/>'
    )


def _pot(traits: PlantTraits) -> str:
    dark, _, accent, light = traits.palette
    if traits.pot_style == 0:
        return (
            f'<rect x="108" y="190" width="84" height="42" rx="8" fill="{accent}"/>'
            f'<rect x="100" y="182" width="100" height="12" rx="6" fill="{dark}"/>'
        )
    if traits.pot_style == 1:
        return (
            f'<path d="M102 182h96l-8 50h-80z" fill="{accent}"/>'
            f'<rect x="100" y="178" width="100" height="12" rx="6" fill="{light}"/>'
        )
    if traits.pot_style == 2:
        return (
            f'<ellipse cx="150" cy="184" rx="50" ry="10" fill="{dark}"/>'
            f'<rect x="104" y="184" width="92" height="48" rx="12" fill="{accent}"/>'
        )
    # pot_style == 3: minimal square with vertical stripes
    return (
        f'<rect x="110" y="182" width="80" height="50" rx="4" fill="{accent}"/>'
        f'<line x1="130" y1="182" x2="130" y2="232" stroke="{dark}" stroke-width="1.5" opacity="0.4"/>'
        f'<line x1="150" y1="182" x2="150" y2="232" stroke="{dark}" stroke-width="1.5" opacity="0.4"/>'
        f'<line x1="170" y1="182" x2="170" y2="232" stroke="{dark}" stroke-width="1.5" opacity="0.4"/>'
        f'<rect x="106" y="178" width="88" height="10" rx="5" fill="{dark}"/>'
    )


def _growth_feature(traits: PlantTraits, seed: str) -> str:
    if traits.growth_feature == 0:
        return ""

    dark, leaf, accent, light = traits.palette
    nums = [int(seed[i: i + 2], 16) for i in range(0, 32, 2)]

    if traits.growth_feature == 1:
        # Tendrils: 2-3 curling arc paths from stem
        parts = []
        for i in range(2 + (nums[10] % 2)):
            start_y = 160 - i * 20
            direction = 1 if i % 2 == 0 else -1
            ex = 150 + direction * (25 + nums[11 + i] % 15)
            ey = start_y - 20
            cx1 = 150 + direction * 10
            cy1 = start_y - 5
            parts.append(
                f'<path d="M 150 {start_y} Q {cx1} {cy1} {ex} {ey}" '
                f'stroke="{leaf}" stroke-width="1.5" fill="none" stroke-linecap="round" opacity="0.7"/>'
            )
        return "".join(parts)

    if traits.growth_feature == 2:
        # Berries: small filled circles near leaf tips
        berries = []
        for i in range(4 + (nums[10] % 4)):
            y = 100 + (i * 18) % 80
            direction = 1 if i % 2 == 0 else -1
            bx = 150 + direction * (22 + nums[11 + i % 4] % 12)
            by = y - 10
            berries.append(f'<circle cx="{bx}" cy="{by}" r="4" fill="{accent}" opacity="0.85"/>')
        return "".join(berries)

    if traits.growth_feature == 3:
        # Secondary plant: small 60% scale beside main pot
        sub_curve = traits.stem_curve // 2
        sub_leaves = []
        for i in range(3):
            y = 175 - i * 12
            direction = -1 if i % 2 == 0 else 1
            lx = 60 + direction * 12
            path = f'M 60 {y} Q {lx} {y - 6} {lx} {y - 14} Q {60 + direction * 4} {y - 8} 60 {y}'
            sub_leaves.append(f'<path d="{path}" fill="{leaf}" opacity="0.75"/>')
        return (
            f'<path d="M60 187 Q {60 + sub_curve} 158 60 132" stroke="{dark}" stroke-width="4" fill="none" stroke-linecap="round"/>'
            + "".join(sub_leaves)
            + f'<circle cx="60" cy="128" r="8" fill="{accent}" opacity="0.8"/>'
            f'<rect x="42" y="187" width="36" height="20" rx="4" fill="{accent}" opacity="0.8"/>'
        )

    if traits.growth_feature == 4:
        # Sparkles: 4-6 tiny 4-pointed stars scattered in background
        sparkles = []
        positions = [(40, 40), (260, 50), (30, 140), (270, 160), (80, 30), (220, 35)]
        for i, (sx, sy) in enumerate(positions[:4 + (nums[10] % 3)]):
            r_outer, r_inner = 5, 2
            pts_list = []
            for j in range(8):
                r = r_outer if j % 2 == 0 else r_inner
                angle = math.radians(j * 45 - 90)
                pts_list.append(f"{sx + r * math.cos(angle):.1f},{sy + r * math.sin(angle):.1f}")
            sparkles.append(f'<polygon points="{" ".join(pts_list)}" fill="{accent}" opacity="0.5"/>')
        return "".join(sparkles)

    # growth_feature == 5: Moss on pot base
    moss_parts = []
    for i in range(5):
        mx = 115 + i * 14
        moss_parts.append(f'<ellipse cx="{mx}" cy="233" rx="7" ry="4" fill="{leaf}" opacity="0.5"/>')
    for i in range(3):
        mx = 122 + i * 18
        moss_parts.append(
            f'<path d="M {mx} 233 Q {mx + 3} 227 {mx + 6} 233" stroke="{leaf}" stroke-width="1.5" fill="none" opacity="0.6"/>'
        )
    return "".join(moss_parts)


def generate_svg(canonical_me_url: str, harvest_urls: list[str] | None = None) -> str:
    base_seed = hashlib.sha256(canonical_me_url.encode("utf-8")).hexdigest()
    if harvest_urls:
        harvest_input = ",".join(sorted(harvest_urls))
        growth_seed = hashlib.sha256(harvest_input.encode("utf-8")).hexdigest()
        combined = hashlib.sha256((base_seed + growth_seed).encode("utf-8")).hexdigest()
    else:
        combined = base_seed

    harvest_count = len(harvest_urls) if harvest_urls else 0
    traits = traits_from_seed(combined, harvest_count)

    leaves = [_leaf_path(i, traits) for i in range(traits.leaf_count)]

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 240" role="img" aria-label="Garden plant">\n'
        f'  {_background(traits)}\n'
        f'  {_growth_feature(traits, combined)}\n'
        f'  {_stem(traits)}\n'
        f'  {"".join(leaves)}\n'
        f'  {_flower(traits)}\n'
        f'  {_pot(traits)}\n'
        f'</svg>'
    )
    return svg
