#!/usr/bin/env python3
"""
Simple wrapper to run iMessage bridge with correct working directory
"""
import sys
import os
import subprocess
from pathlib import Path

# Change to server directory
server_dir = Path(__file__).parent / "server"
os.chdir(server_dir)

# Run the bridge script directly
bridge_path = server_dir / "services" / "imessage" / "imessage_bridge.py"
result = subprocess.run([sys.executable, str(bridge_path)] + sys.argv[1:], 
                       capture_output=True, text=True)

# Exit with the same code
sys.stdout.write(result.stdout)
sys.stderr.write(result.stderr)
sys.exit(result.returncode)
