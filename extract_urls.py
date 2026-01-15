#!/usr/bin/env python3
"""
Extract tab URLs and metadata from Ultimate Guitar "My Tabs" HTML export.

Usage:
    python extract_urls.py [html_file]

If no file is specified, uses guiltar_tabs.html from current directory.
"""

import json
import re
import sys
from pathlib import Path
from html import unescape

from config import HTML_FILE, URLS_FILE


def extract_tabs_from_html(html_content: str) -> list[dict]:
    """
    Extract tab information from Ultimate Guitar HTML export.

    Properly parses the embedded JSON data by:
    1. Finding the js-store data-content attribute
    2. Decoding HTML entities to get valid JSON
    3. Parsing the JSON and extracting tab entries

    Uses URL as primary key since it's unique per tab.
    """
    # Find the js-store data-content attribute which contains the JSON
    match = re.search(r'class="js-store"[^>]*data-content="([^"]+)"', html_content)

    if not match:
        print("Warning: Could not find js-store data. Falling back to regex extraction.")
        return _fallback_regex_extraction(html_content)

    # Decode HTML entities to get valid JSON
    json_str = unescape(match.group(1))

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse JSON: {e}. Falling back to regex extraction.")
        return _fallback_regex_extraction(html_content)

    # Navigate to the tabs data - structure is data.store.page.data.tabs
    try:
        tabs_data = data.get("store", {}).get("page", {}).get("data", {}).get("tabs", [])
    except (KeyError, TypeError):
        tabs_data = []

    if not tabs_data:
        # Try alternative path
        print("Warning: No tabs found at expected path. Searching for tab entries...")
        return _search_json_for_tabs(data)

    # Build dict keyed by URL (primary key) to deduplicate
    tabs_by_url = {}
    for tab in tabs_data:
        url = tab.get("song_url", "")
        if url and url.startswith("https://tabs.ultimate-guitar.com/tab/"):
            if url not in tabs_by_url:
                tabs_by_url[url] = {
                    "url": url,
                    "song_name": tab.get("song_name", "Unknown"),
                    "band_name": tab.get("band_name", "Unknown"),
                    "type": tab.get("type", "Tab"),
                }

    return list(tabs_by_url.values())


def _search_json_for_tabs(data: dict, tabs_found: dict = None) -> list[dict]:
    """Recursively search JSON structure for tab entries."""
    if tabs_found is None:
        tabs_found = {}

    if isinstance(data, dict):
        # Check if this dict looks like a tab entry
        if "song_url" in data and "song_name" in data:
            url = data.get("song_url", "")
            if url.startswith("https://tabs.ultimate-guitar.com/tab/") and url not in tabs_found:
                tabs_found[url] = {
                    "url": url,
                    "song_name": data.get("song_name", "Unknown"),
                    "band_name": data.get("band_name", "Unknown"),
                    "type": data.get("type", "Tab"),
                }
        # Recurse into dict values
        for value in data.values():
            _search_json_for_tabs(value, tabs_found)
    elif isinstance(data, list):
        for item in data:
            _search_json_for_tabs(item, tabs_found)

    return list(tabs_found.values())


def _fallback_regex_extraction(html_content: str) -> list[dict]:
    """
    Fallback regex-based extraction if JSON parsing fails.
    Decodes HTML entities first to handle & in names.
    """
    # First decode the entire relevant section
    decoded = unescape(html_content)

    # Now search for tab entries in decoded content
    entry_pattern = (
        r'"song_name":"([^"]+)",'
        r'"band_name":"([^"]+)",'
        r'"song_url":"(https://tabs\.ultimate-guitar\.com/tab/[^"]+)",'
        r'"band_url":"[^"]*",'
        r'"type":"([^"]+)"'
    )

    matches = re.findall(entry_pattern, decoded)

    tabs_by_url = {}
    for song_name, band_name, url, tab_type in matches:
        if url not in tabs_by_url:
            tabs_by_url[url] = {
                "url": url,
                "song_name": song_name,
                "band_name": band_name,
                "type": tab_type,
            }

    return list(tabs_by_url.values())


def main():
    # Determine input file
    if len(sys.argv) > 1:
        html_file = Path(sys.argv[1])
    else:
        html_file = Path(HTML_FILE)

    if not html_file.exists():
        print(f"Error: File not found: {html_file}")
        print(f"\nTo get this file:")
        print(f"  1. Go to https://www.ultimate-guitar.com/user/mytabs")
        print(f"  2. Log in to your account")
        print(f"  3. Save the page as HTML (File -> Save Page As)")
        print(f"  4. Save it as '{HTML_FILE}' in this directory")
        sys.exit(1)

    print(f"Reading {html_file}...")
    html_content = html_file.read_text(encoding="utf-8")

    print("Extracting tab URLs...")
    tabs = extract_tabs_from_html(html_content)

    if not tabs:
        print("Error: No tabs found in the HTML file.")
        print("Make sure you saved the complete 'My Tabs' page from Ultimate Guitar.")
        sys.exit(1)

    # Save to JSON
    output_file = Path(URLS_FILE)
    output_file.write_text(json.dumps(tabs, indent=2), encoding="utf-8")

    print(f"\nExtracted {len(tabs)} tabs")
    print(f"Saved to: {output_file}")

    # Show summary by type
    types = {}
    for tab in tabs:
        t = tab["type"]
        types[t] = types.get(t, 0) + 1

    print("\nBreakdown by type:")
    for tab_type, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {tab_type}: {count}")

    # Show a few examples
    print("\nFirst 5 tabs:")
    for tab in tabs[:5]:
        print(f"  - {tab['band_name']} - {tab['song_name']} ({tab['type']})")


if __name__ == "__main__":
    main()
