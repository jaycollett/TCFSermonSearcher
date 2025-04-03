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
    # Get the base directory (one level up from this script)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Extract messages
    extract_cmd = ["pybabel", "extract", "-F", os.path.join(base_dir, "babel.cfg"), 
                  "-o", os.path.join(base_dir, "messages.pot"), base_dir]
    print("Extracting messages...")
    subprocess.check_call(extract_cmd)

    # Update translations
    translations_dir = os.path.join(base_dir, "translations")
    update_cmd = ["pybabel", "update", "-i", os.path.join(base_dir, "messages.pot"), 
                 "-d", translations_dir]
    print("Updating translation files...")
    subprocess.check_call(update_cmd)

    # Compile translations
    compile_cmd = ["pybabel", "compile", "-d", translations_dir]
    print("Compiling translation files...")
    subprocess.check_call(compile_cmd)

    print("Translation update completed successfully!")

if __name__ == "__main__":
    # Run the translation update
    update_translations()