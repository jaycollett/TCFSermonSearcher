# Build Utilities

This directory contains utilities for building and preparing the TCF Sermon Searcher application.

## Scripts

- `download_bootstrap.py` - Downloads Bootstrap CSS and JS files for local use
- `update_translations.py` - Extracts messages and updates translations

## Configuration Files

- `babel.cfg` - Configuration for Babel translation extraction
- `messages.pot` - Template file for translations (auto-generated)

## Usage

These scripts should be run from the project root directory:

```bash
# Download Bootstrap
python build_utils/download_bootstrap.py

# Update translations
python build_utils/update_translations.py
```