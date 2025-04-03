#!/usr/bin/env python
"""
TCF Sermon Searcher Version Update Script

This script updates the version and release date in the __init__.py file.
Usage: python update_version.py [new_version] [release_date]
Example: python update_version.py 0.4.13 "April 15, 2025"

If no arguments are provided, the script will increment the patch version and use today's date.
"""

import sys
import os
import re
import datetime
from pathlib import Path

INIT_FILE = Path(__file__).parent / "sermon_search" / "__init__.py"

def update_version(new_version=None, release_date=None):
    """
    Update the version and release date in __init__.py file.
    
    Args:
        new_version: The new version string to set. If None, increments the patch version.
        release_date: The release date string to set. If None, uses today's date.
    """
    # Read the current __init__.py file
    with open(INIT_FILE, 'r') as f:
        content = f.read()
    
    # Extract current version
    version_match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if not version_match:
        print("Error: Could not find __version__ in the __init__.py file.")
        return False
    
    current_version = version_match.group(1)
    
    # Determine new version if not provided
    if not new_version:
        # Parse current version components
        version_parts = current_version.split('.')
        if len(version_parts) != 3:
            print(f"Error: Invalid version format: {current_version}")
            return False
        
        # Increment patch version
        major, minor, patch = version_parts
        patch = str(int(patch) + 1)
        new_version = f"{major}.{minor}.{patch}"
    
    # Determine release date if not provided
    if not release_date:
        today = datetime.datetime.now()
        release_date = today.strftime("%B %d, %Y")
    
    # Update version in file
    new_content = re.sub(
        r'__version__\s*=\s*["\']([^"\']+)["\']',
        f'__version__ = "{new_version}"',
        content
    )
    
    # Update or add release date
    if '__release_date__' in new_content:
        new_content = re.sub(
            r'__release_date__\s*=\s*["\']([^"\']+)["\']',
            f'__release_date__ = "{release_date}"',
            new_content
        )
    else:
        # Add release date if not present
        new_content = new_content.replace(
            f'__version__ = "{new_version}"',
            f'__version__ = "{new_version}"\n__release_date__ = "{release_date}"'
        )
    
    # Write updated content back to file
    with open(INIT_FILE, 'w') as f:
        f.write(new_content)
    
    print(f"Updated version to {new_version} and release date to {release_date}")
    print("Now, you need to update the translations by running:")
    print("  python -m build_utils.update_translations")
    return True

if __name__ == "__main__":
    new_version = sys.argv[1] if len(sys.argv) > 1 else None
    release_date = sys.argv[2] if len(sys.argv) > 2 else None
    
    update_version(new_version, release_date)