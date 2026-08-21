#!/usr/bin/env python3
"""
tuqueque bootstrap script — bridges config → browser launch → CDP relay.
"""
import sys
import os
# Ensure the package source is on the path (especially when run directly)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from tuqueque.config import get_browser_config, get_browser_args, get_launch_options