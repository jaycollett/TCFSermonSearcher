#!/usr/bin/env python
"""
Script to download Bootstrap CSS and JS files for local use.

This script fetches Bootstrap files and saves them locally to reduce dependency
on external CDNs and improve site performance.
"""

import os
import urllib.request

def download_file(url, save_path):
    """Download a file from a URL and save it to the specified path."""
    print(f"Downloading {url} to {save_path}...")
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    urllib.request.urlretrieve(url, save_path)
    print(f"Downloaded {os.path.basename(save_path)} successfully.")

def main():
    """Download Bootstrap CSS and JS files."""
    # Use the static directory relative to this file location
    base_dir = os.path.dirname(os.path.abspath(__file__))
    css_path = os.path.join(base_dir, "static", "css")
    js_path = os.path.join(base_dir, "static", "js")
    
    # Create directories if they don't exist
    os.makedirs(css_path, exist_ok=True)
    os.makedirs(js_path, exist_ok=True)
    
    # Download Bootstrap CSS
    bootstrap_css_url = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
    bootstrap_css_path = os.path.join(css_path, "bootstrap.min.css")
    download_file(bootstrap_css_url, bootstrap_css_path)
    
    # Download Bootstrap JS
    bootstrap_js_url = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"
    bootstrap_js_path = os.path.join(js_path, "bootstrap.bundle.min.js")
    download_file(bootstrap_js_url, bootstrap_js_path)
    
    print("Bootstrap files have been downloaded successfully!")

if __name__ == "__main__":
    main()