#!/usr/bin/env python
"""
Script to extract messages and update translations for TCF Sermon Searcher.

This script extracts translatable strings, updates the .po files, and compiles them to .mo files.
"""

import os
import subprocess
import sys

def update_translations():
    """Update and compile all translations."""
    # Extract messages
    extract_cmd = ["pybabel", "extract", "-F", "babel.cfg", "-o", "messages.pot", "."]
    print("Extracting messages...")
    subprocess.check_call(extract_cmd)

    # Update translations
    update_cmd = ["pybabel", "update", "-i", "messages.pot", "-d", "translations"]
    print("Updating translation files...")
    subprocess.check_call(update_cmd)

    # Compile translations
    compile_cmd = ["pybabel", "compile", "-d", "translations"]
    print("Compiling translation files...")
    subprocess.check_call(compile_cmd)

    print("Translation update completed successfully!")

if __name__ == "__main__":
    # Ensure the script is run from the project root directory
    if not os.path.exists("babel.cfg"):
        print("Error: This script must be run from the project root directory.")
        sys.exit(1)
    
    update_translations()