#!/usr/bin/env python3
"""
Start Dashboard - Direct Script
Runs dashboard using .venv packages
"""

import sys
import os

# Add .venv site-packages FIRST
script_dir = os.path.dirname(os.path.abspath(__file__))
venv_site = os.path.join(script_dir, '.venv', 'lib', 'python3.13', 'site-packages')
sys.path.insert(0, venv_site)
sys.path.insert(0, script_dir)

# Verify uvicorn is available
try:
    import uvicorn
except ImportError:
    print(f"ERROR: uvicorn not found in {venv_site}")
    print(f"Please install: pip install uvicorn")
    sys.exit(1)

# Now import and run
from src.cli.start_dashboard import main

if __name__ == '__main__':
    sys.exit(main())
