from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class PlantTraits:
    stem_curve: int
    leaf_count: int
    flower_style: int
    pot_style: int
    palette: tuple[str, str, str, str]


PALETTES = [
    ("#1b4332", "#2d6a4f", "#74c69d", "#e9f5db"),
    ("#386641", "#6a994e", "#a7c957", "#f2e8cf"),
    ("#344e41", "#3a5a40", "#588157", "#dad7cd"),
    ("#283618", "#606c38", "#dda15e", "#fefae0"),
]


def traits_from_seed(seed: str) -> PlantTraits:
    numbers = [int(seed[i : i + 2], 16) for i in range(0, 20, 2)]
    palette = PALETTES[numbers[0] % len(PALETTES)]
    return PlantTraits(
        stem_curve=(numbers[1] % 40) - 20,
        leaf_count=4 + (numbers[2] % 5),
        flower_style=numbers[3] % 3,
        pot_style=numbers[4] % 3,
        palette=palette,
    )


def _flower(traits: PlantTraits) -> str:
    _, leaf, accent, light = traits.palette
    if traits.flower_style == 0:
        return (
            f'<circle cx="150" cy="75" r="14" fill="{accent}"/>'
            f'<circle cx="150" cy="75" r="6" fill="{light}"/>'
        )
    if traits.flower_style == 1:
        return (
            f'<rect x="140" y="64" width="20" height="20" rx="6" fill="{accent}"/>'
            f'<circle cx="150" cy="74" r="5" fill="{leaf}"/>'
        )
    return (
        f'<polygon points="150,58 162,86 138,86" fill="{accent}"/>'
        f'<circle cx="150" cy="76" r="5" fill="{light}"/>'
    )


def _pot(traits: PlantTraits) -> str:
    dark, _, accent, light = traits.palette
    if traits.pot_style == 0:
        return f'<rect x="108" y="190" width="84" height="42" rx="8" fill="{accent}"/><rect x="100" y="182" width="100" height="12" rx="6" fill="{dark}"/>'
    if traits.pot_style == 1:
        return f'<path d="M102 182h96l-8 50h-80z" fill="{accent}"/><rect x="100" y="178" width="100" height="12" rx="6" fill="{light}"/>'
    return f'<ellipse cx="150" cy="184" rx="50" ry="10" fill="{dark}"/><rect x="104" y="184" width="92" height="48" rx="12" fill="{accent}"/>'


def generate_svg(canonical_me_url: str) -> str:
    seed = hashlib.sha256(canonical_me_url.encode("utf-8")).hexdigest()
    traits = traits_from_seed(seed)
    dark, leaf, accent, light = traits.palette
    control_x = 150 + traits.stem_curve

    leaves = []
    for idx in range(traits.leaf_count):
        y = 165 - idx * 16
        direction = -1 if idx % 2 == 0 else 1
        lx = 150 + direction * (18 + idx)
        leaf_path = (
            f'M 150 {y} Q {lx} {y - 8} {lx} {y - 18} '
            f'Q {150 + direction * 6} {y - 10} 150 {y}'
        )
        leaves.append(f'<path d="{leaf_path}" fill="{leaf}" opacity="0.9"/>')

    svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 240" role="img" aria-label="Garden plant">
  <rect width="300" height="240" fill="{light}"/>
  <path d="M150 184 Q {control_x} 120 150 80" stroke="{dark}" stroke-width="6" fill="none" stroke-linecap="round"/>
  {''.join(leaves)}
  {_flower(traits)}
  {_pot(traits)}
</svg>
""".strip()
    return svg
