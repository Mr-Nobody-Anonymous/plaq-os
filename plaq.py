#!/usr/bin/env python3
"""Root entrypoint script for Plaq-OS CLI."""

import sys
import plaq_bootstrap  # noqa: F401
from plaq_cli.main import configure_stdio, main

if __name__ == "__main__":
    configure_stdio()
    sys.exit(main())
