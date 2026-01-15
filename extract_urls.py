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

    Parses each complete tab entry as a unit to keep fields properly correlated.
    Uses URL as primary key since it's unique per tab.
    """
    # Pattern to match a complete tab entry with all fields together
    # Entry format: "song_name":"...","band_name":"...","song_url":"...","band_url":"...","type":"..."
    entry_pattern = (
        r'song_name&quot;:&quot;([^&]+)&quot;,'
        r'&quot;band_name&quot;:&quot;([^&]+)&quot;,'
        r'&quot;song_url&quot;:&quot;(https://tabs\.ultimate-guitar\.com/tab/[^&]+)&quot;,'
        r'&quot;band_url&quot;:[^,]+,'
        r'&quot;type&quot;:&quot;([^&]+)&quot;'
    )

    matches = re.findall(entry_pattern, html_content)

    # Build dict keyed by URL (primary key) to deduplicate
    tabs_by_url = {}
    for song_name, band_name, url, tab_type in matches:
        # URL is unique - use as primary key
        if url not in tabs_by_url:
            tabs_by_url[url] = {
                "url": unescape(url),
                "song_name": unescape(song_name),
                "band_name": unescape(band_name),
                "type": unescape(tab_type),
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
