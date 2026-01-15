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

    The HTML contains JSON data with tab entries. Fields are HTML-encoded:
    song_url&quot;:&quot;https://tabs.ultimate-guitar.com/tab/...&quot;
    song_name&quot;:&quot;Mr Jones&quot;
    band_name&quot;:&quot;Counting Crows&quot;
    type&quot;:&quot;Chords&quot;
    """
    tabs = []

    # Extract each field separately using simple patterns
    # song_url comes before band_url, so we use that boundary
    url_pattern = r'song_url&quot;:&quot;(https://tabs\.ultimate-guitar\.com/tab/[^&]+)&quot;'
    song_pattern = r'song_name&quot;:&quot;([^&]+)&quot;'
    band_pattern = r'band_name&quot;:&quot;([^&]+)&quot;'
    type_pattern = r'&quot;type&quot;:&quot;(Chords|Tab|Bass|Ukulele|Power|Pro|Video|Drums)[^&]*&quot;'

    urls = re.findall(url_pattern, html_content)
    songs = re.findall(song_pattern, html_content)
    bands = re.findall(band_pattern, html_content)
    types = re.findall(type_pattern, html_content)

    # The lists should be the same length if we're extracting correctly
    # Use the URL list as the primary since that's what we need
    min_len = min(len(urls), len(songs), len(bands), len(types))

    if min_len == 0:
        # Fallback: just extract URLs and derive info from URL
        for url in urls:
            # Parse URL: /tab/artist/song-name-type-id
            parts = url.split("/tab/")[-1].split("/")
            if len(parts) >= 2:
                artist = parts[0].replace("-", " ").title()
                song_part = parts[1]
                # Try to extract type from URL
                tab_type = "Chords" if "chords" in song_part else "Tab"
                song_name = re.sub(r'-(chords|tabs|tab)-\d+$', '', song_part)
                song_name = song_name.replace("-", " ").title()

                tabs.append({
                    "url": url,
                    "song_name": song_name,
                    "band_name": artist,
                    "type": tab_type,
                })
        return tabs

    seen_urls = set()
    for i in range(min_len):
        url = urls[i]

        # Skip duplicates
        if url in seen_urls:
            continue
        seen_urls.add(url)

        tabs.append({
            "url": unescape(url),
            "song_name": unescape(songs[i]),
            "band_name": unescape(bands[i]),
            "type": unescape(types[i]),
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
