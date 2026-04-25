#!/usr/bin/env python3
"""
Integration helper script for Amjad Jarvis CLI.

Run this once to wire Jarvis commands into the main agency CLI.
After running, 'agency amjad' commands will work globally.
"""

import sys
from pathlib import Path


def integrate_cli():
    """Add amjad_group to main CLI."""
    cli_path = Path(__file__).parent.parent / "runtime" / "agency" / "cli.py"
    
    if not cli_path.exists():
        print(f"❌ CLI file not found at {cli_path}")
        return False
    
    content = cli_path.read_text()
    
    # Check if already integrated
    if "amjad_jarvis_cli" in content:
        print("✓ Amjad Jarvis already integrated into CLI")
        return True
    
    # Add import
    import_line = "from .amjad_jarvis_cli import amjad_group\n"
    if "from .server import build_app" in content:
        content = content.replace(
            "from .server import build_app",
            "from .server import build_app\nfrom .amjad_jarvis_cli import amjad_group",
        )
    else:
        content = content.replace(
            "from .logging import configure as configure_logging",
            "from .logging import configure as configure_logging\n" + import_line,
        )
    
    # Add command to main group
    wire_line = """
@main.group()
def amjad():
    \"\"\"Amjad Jarvis Meta-Orchestrator commands.\"\"\"
    pass

# Wire subcommands
amjad.add_command(amjad_group.profile)
amjad.add_command(amjad_group.trust)
amjad.add_command(amjad_group.shell)
amjad.add_command(amjad_group.web_search)
amjad.add_command(amjad_group.code_exec)
amjad.add_command(amjad_group.computer_use)
amjad.add_command(amjad_group.run_request)
amjad.add_command(amjad_group.show_status)

"""
    
    # Insert before final if __name__
    if "if __name__ == \"__main__\":" in content:
        content = content.replace(
            "if __name__ == \"__main__\":",
            wire_line + "if __name__ == \"__main__\":",
        )
    
    cli_path.write_text(content)
    print(f"✓ Integrated Amjad Jarvis into {cli_path}")
    return True


if __name__ == "__main__":
    success = integrate_cli()
    sys.exit(0 if success else 1)
