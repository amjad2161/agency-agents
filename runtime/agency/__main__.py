"""Allow `python -m agency` as an alias for `python -m agency.cli`."""
from agency.cli import main

if __name__ == "__main__":
    main()
