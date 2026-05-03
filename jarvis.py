"""JARVIS BRAINIAC — Main Entry Point.
Usage: python -m jarvis [command] [options]
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runtime.agency.cli import cli

if __name__ == "__main__":
    cli()
