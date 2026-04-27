#!/usr/bin/env python3
"""Build JARVIS_CAPABILITIES.md from the jarvis/ directory.

Walks every `jarvis-*.md` file, extracts the H1 title and the first
non-empty paragraph after the title, infers a category from the slug,
and emits a single capability registry document.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple


CATEGORIES: list[tuple[str, str, list[str]]] = [
    # (category_id, display_name, slug-prefix matchers)
    ("core", "Core Intelligence", ["core", "core-brain", "brainiac", "human-interface"]),
    ("engineering", "Engineering & Software", [
        "engineering", "devops-platform", "embedded-firmware", "iot-robotics",
        "computer-use", "automation", "testing-qa", "omega-engineer",
    ]),
    ("ai-data", "AI, Data & Knowledge", [
        "ai-ml", "data-intelligence", "knowledge-research", "linguistics-nlp",
        "voice-speech", "cognitive-learning",
    ]),
    ("design-creative", "Design, Creative & Media", [
        "design-creative", "creative-writing", "art-history-culture",
        "photography-visual-arts", "music-production", "media-entertainment",
        "content-media", "creator-economy", "fashion-luxury", "omega-creative",
    ]),
    ("ar-xr-spatial", "AR/XR, Spatial & Frontier", [
        "ar-xr-spatial", "digital-twin", "future-tech", "quantum-computing",
        "nanotechnology", "neuroscience-bci",
    ]),
    ("strategy-ops", "Strategy, Ops & Leadership", [
        "strategy-ops", "product-management", "project-management",
        "ops-support", "entrepreneur-startup", "omega-operator",
    ]),
    ("finance-economy", "Finance & Economy", [
        "finance", "fintech-payments", "quant-finance", "behavioral-economics",
        "insurance-risk", "climate-finance",
    ]),
    ("security-defense", "Security, Defense & Risk", [
        "security-cyber", "red-team", "military-defense", "privacy-data-governance",
    ]),
    ("health-life", "Health, Life Sciences & Wellbeing", [
        "biotech-medicine", "genomics-precision-medicine", "health-biometrics",
        "healthcare-ops", "mental-health", "wellness-fitness-tech",
        "elder-care-aging", "veterinary-animal-science", "pet-care-tech",
        "sports-performance",
    ]),
    ("sustainability", "Climate, Energy & Sustainability", [
        "climate-tech", "climate-adaptation", "climate-sustainability",
        "energy-systems", "nuclear-energy", "circular-economy",
        "water-resources", "materials-chemistry", "food-agritech",
    ]),
    ("commerce-marketing", "Commerce, Marketing & Growth", [
        "e-commerce-retail-tech", "marketing-global", "paid-media",
        "sales-growth", "customer-experience", "event-tech",
    ]),
    ("infra-built-env", "Infrastructure & Built Environment", [
        "architecture-built-env", "construction-proptech", "real-estate-proptech",
        "smart-cities", "transportation-mobility-tech", "automotive-ev",
        "supply-chain-logistics", "manufacturing-industry", "maritime-ocean",
        "space-aerospace", "geospatial-mapping",
    ]),
    ("public-policy", "Public Sector, Policy & Society", [
        "policy-governance", "legal-compliance", "legaltech",
        "immigration-global-mobility", "philanthropy-impact",
        "social-entrepreneurship", "nonprofits-social-impact",
        "philosophy-ethics", "journalism-research",
    ]),
    ("education-people", "Education, People & Culture", [
        "education-learning", "future-of-work", "hr-people-ops",
        "parenting-family", "translation-localization", "accessibility-inclusive-tech",
    ]),
    ("emerging-niche", "Emerging & Specialized Domains", [
        "academic-science", "esports-gaming-industry", "game-world",
        "sports-analytics", "travel-hospitality", "web3-blockchain",
        "disaster-emergency-management",
    ]),
    ("misc", "Misc & Cross-Cutting", []),  # catch-all
]


class ModuleEntry(NamedTuple):
    slug: str
    title: str
    description: str
    file: str


def parse_module(path: Path) -> ModuleEntry:
    slug = path.stem.removeprefix("jarvis-")
    text = path.read_text(encoding="utf-8", errors="replace")

    title = slug.replace("-", " ").title()
    description = ""

    title_match = re.search(r"^#\s+(.+?)\s*$", text, flags=re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()
        # Strip leading emoji/markdown decorations (most jarvis files
        # start the H1 with an emoji + space).
        title = re.sub(r"^[^A-Za-z0-9]+", "", title).strip() or title

    # First non-empty, non-blockquote, non-heading paragraph after H1.
    after = text[title_match.end():] if title_match else text
    paragraph: list[str] = []
    for raw in after.splitlines():
        line = raw.strip()
        if not line:
            if paragraph:
                break
            continue
        if line.startswith("#"):
            if paragraph:
                break
            continue
        if line.startswith(">") or line.startswith("|"):
            continue
        if line.startswith("```"):
            break
        paragraph.append(line)
        if sum(len(p) for p in paragraph) > 240:
            break
    description = " ".join(paragraph)
    description = re.sub(r"\s+", " ", description).strip()
    if len(description) > 220:
        description = description[:217].rstrip() + "..."
    if not description:
        description = f"{title} domain module."

    return ModuleEntry(slug=slug, title=title, description=description, file=path.name)


def categorize(slug: str) -> str:
    for cat_id, _name, prefixes in CATEGORIES:
        for p in prefixes:
            if slug == p:
                return cat_id
    # No exact match — fall through to misc.
    return "misc"


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    jarvis_dir = repo / "jarvis"
    if not jarvis_dir.is_dir():
        print(f"jarvis dir missing: {jarvis_dir}", file=sys.stderr)
        return 1
    files = sorted(p for p in jarvis_dir.glob("jarvis-*.md"))
    modules = [parse_module(p) for p in files]

    by_cat: dict[str, list[ModuleEntry]] = {c[0]: [] for c in CATEGORIES}
    for m in modules:
        by_cat[categorize(m.slug)].append(m)

    out = repo / "JARVIS_CAPABILITIES.md"
    lines: list[str] = []
    lines.append("# JARVIS Capability Registry")
    lines.append("")
    lines.append(
        f"> Auto-generated from `jarvis/*.md`. **{len(modules)} domain "
        f"modules across {sum(1 for _, _, ms in [(c, n, by_cat[c]) for c, n, _ in CATEGORIES] if ms)} active categories.**"
    )
    lines.append("")
    lines.append(
        "Regenerate with `python scripts/build_capabilities.py`. "
        "Each module is a self-contained persona file in `jarvis/`."
    )
    lines.append("")
    lines.append("## Counts at a Glance")
    lines.append("")
    lines.append(f"- **Total modules**: {len(modules)}")
    lines.append(f"- **Total categories**: {sum(1 for c, _n, _ in CATEGORIES if by_cat[c])}")
    lines.append(f"- **Source files scanned**: {len(files)}")
    lines.append("")
    lines.append("| Category | Modules |")
    lines.append("|----------|---------|")
    for cat_id, name, _ in CATEGORIES:
        n = len(by_cat[cat_id])
        if n:
            lines.append(f"| {name} | {n} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    for cat_id, name, _ in CATEGORIES:
        ms = sorted(by_cat[cat_id], key=lambda m: m.slug)
        if not ms:
            continue
        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"_{len(ms)} module{'s' if len(ms) != 1 else ''}._")
        lines.append("")
        lines.append("| Slug | Title | File | Description |")
        lines.append("|------|-------|------|-------------|")
        for m in ms:
            desc = m.description.replace("|", "\\|")
            lines.append(
                f"| `{m.slug}` | {m.title} | [`{m.file}`](jarvis/{m.file}) | {desc} |"
            )
        lines.append("")

    lines.append("## Specialist Agents")
    lines.append("")
    lines.append(
        "Each domain module ships with a persona body designed to expand "
        "into 1-3 specialist sub-agents at runtime. Specialist counts are "
        "advisory and depend on task decomposition; the registry guarantees "
        "*coverage* (every domain has a home), not a fixed agent count per slug."
    )
    lines.append("")
    lines.append(f"Estimated specialist envelope: **{len(modules)*3} max**, "
                 f"**{len(modules)} guaranteed**.")
    lines.append("")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(modules)} modules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
