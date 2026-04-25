"""List every skill the runtime knows about, grouped by category.

No API key needed.

    python runtime/examples/01_list_skills.py
"""

from agency.skills import SkillRegistry


def main() -> None:
    reg = SkillRegistry.load()
    print(f"Loaded {len(reg)} skills across {len(reg.categories())} categories.\n")
    for category in reg.categories():
        skills = reg.by_category(category)
        print(f"## {category} ({len(skills)})")
        for s in skills[:5]:  # first five per category
            print(f"  {s.emoji} {s.name:38s} — {s.description[:60]}")
        if len(skills) > 5:
            print(f"  … and {len(skills) - 5} more")
        print()


if __name__ == "__main__":
    main()
