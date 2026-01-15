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


def parse_url_info(url: str) -> dict:
    """
    Extract artist, song name, and type from a tab URL.

    URL format: https://tabs.ultimate-guitar.com/tab/artist-name/song-name-type-id
    Example: https://tabs.ultimate-guitar.com/tab/counting-crows/mr-jones-chords-16066
    """
    # Parse URL: /tab/artist/song-name-type-id
    parts = url.split("/tab/")[-1].split("/")
    if len(parts) >= 2:
        artist = parts[0].replace("-", " ").title()
        song_part = parts[1]

        # Determine tab type from URL
        if "-chords-" in song_part:
            tab_type = "Chords"
            song_name = re.sub(r'-chords-\d+$', '', song_part)
        elif "-ukulele-chords-" in song_part:
            tab_type = "Ukulele"
            song_name = re.sub(r'-ukulele-chords-\d+$', '', song_part)
        elif "-tabs-" in song_part:
            tab_type = "Tab"
            song_name = re.sub(r'-tabs-\d+$', '', song_part)
        elif "-tab-" in song_part:
            tab_type = "Tab"
            song_name = re.sub(r'-tab-\d+$', '', song_part)
        elif "-bass-" in song_part:
            tab_type = "Bass"
            song_name = re.sub(r'-bass-\d+$', '', song_part)
        else:
            # Fallback: remove trailing -word-number pattern
            tab_type = "Tab"
            song_name = re.sub(r'-[a-z]+-\d+$', '', song_part)

        song_name = song_name.replace("-", " ").title()

        return {
            "song_name": song_name,
            "band_name": artist,
            "type": tab_type,
        }

    return {"song_name": "Unknown", "band_name": "Unknown", "type": "Tab"}


def extract_tabs_from_html(html_content: str) -> list[dict]:
    """
    Extract tab URLs from Ultimate Guitar HTML export.

    Extracts all unique tab URLs and derives metadata from the URL itself.
    This is more reliable than trying to correlate separate field extractions.
    """
    tabs = []

    # Extract all tab URLs
    url_pattern = r'song_url&quot;:&quot;(https://tabs\.ultimate-guitar\.com/tab/[^&]+)&quot;'
    urls = re.findall(url_pattern, html_content)

    seen_urls = set()
    for url in urls:
        # Skip duplicates
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Derive metadata from URL (reliable, always matches the actual tab)
        info = parse_url_info(url)

        tabs.append({
            "url": url,
            "song_name": info["song_name"],
            "band_name": info["band_name"],
            "type": info["type"],
        })

    return tabs


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
