#!/usr/bin/env python3
"""Root entrypoint script for Plaq-OS CLI."""

import sys
import plaq_bootstrap
from plaq_cli.main import main

if __name__ == "__main__":
    sys.exit(main())
