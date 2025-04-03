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
    # Get root directory (parent of build_utils)
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Set paths relative to locations
    build_utils_dir = os.path.dirname(os.path.abspath(__file__))
    babel_cfg_path = os.path.join(build_utils_dir, "babel.cfg")
    messages_pot_path = os.path.join(build_utils_dir, "messages.pot")
    translations_dir = os.path.join(root_dir, "translations")
    
    # Extract messages
    extract_cmd = ["pybabel", "extract", "-F", babel_cfg_path, "-o", messages_pot_path, root_dir]
    print("Extracting messages...")
    subprocess.check_call(extract_cmd)

    # Update translations
    update_cmd = ["pybabel", "update", "-i", messages_pot_path, "-d", translations_dir]
    print("Updating translation files...")
    subprocess.check_call(update_cmd)

    # Compile translations
    compile_cmd = ["pybabel", "compile", "-d", translations_dir]
    print("Compiling translation files...")
    subprocess.check_call(compile_cmd)

    print("Translation update completed successfully!")

if __name__ == "__main__":
    # Get build_utils directory
    build_utils_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Ensure babel.cfg exists
    if not os.path.exists(os.path.join(build_utils_dir, "babel.cfg")):
        print("Error: babel.cfg not found in build_utils directory.")
        sys.exit(1)
    
    update_translations()