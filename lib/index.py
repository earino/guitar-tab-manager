"""
Index building, loading, and saving for guitar tabs.
"""

import json
from datetime import datetime
from pathlib import Path

from . import parser


def build_index(tabs_dir: Path, verbose: bool = False) -> dict:
    """
    Build an index from all tab files in the directory.

    Returns a dict with metadata for each tab, keyed by file path.
    """
    index = {
        "version": 1,
        "built_at": datetime.now().isoformat(),
        "tabs_dir": str(tabs_dir),
        "tabs": {},
    }

    tab_files = list(tabs_dir.glob("**/*.txt"))

    if verbose:
        print(f"Found {len(tab_files)} tab files")

    for i, path in enumerate(tab_files, 1):
        if verbose and i % 50 == 0:
            print(f"Processing {i}/{len(tab_files)}...")

        try:
            tab_data = parser.parse_tab_file(path)

            # Extract additional metadata
            content = tab_data["content"]
            chords = parser.extract_chords(content)
            sections = parser.extract_sections(content)
            lyrics = parser.has_lyrics(content)
            key = parser.detect_key(content, chords)

            entry = {
                "file_path": str(path),
                "song": tab_data["song"],
                "artist": tab_data["artist"],
                "type": tab_data["type"],
                "url": tab_data["url"],
                "capo": tab_data["capo"],
                "chords": chords,
                "key": key,
                "sections": sections,
                "has_lyrics": lyrics,
                # Placeholders for LLM enrichment
                "mood": None,
                "themes": None,
                "tempo_feel": None,
            }

            index["tabs"][str(path)] = entry

        except Exception as e:
            if verbose:
                print(f"Error processing {path}: {e}")

    if verbose:
        print(f"Indexed {len(index['tabs'])} tabs")

    return index


def save_index(index: dict, path: Path):
    """Save the index to a JSON file."""
    path.write_text(json.dumps(index, indent=2), encoding="utf-8")


def load_index(path: Path) -> dict | None:
    """Load the index from a JSON file. Returns None if file doesn't exist."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def get_stats(index: dict) -> dict:
    """Get statistics about the index."""
    tabs = index.get("tabs", {})

    # Count by type
    types = {}
    for tab in tabs.values():
        t = tab.get("type", "Unknown")
        types[t] = types.get(t, 0) + 1

    # Count unique artists
    artists = set(tab.get("artist") for tab in tabs.values() if tab.get("artist"))

    # Count tabs with lyrics
    with_lyrics = sum(1 for tab in tabs.values() if tab.get("has_lyrics"))

    # Count tabs with mood (enriched)
    enriched = sum(1 for tab in tabs.values() if tab.get("mood"))

    # Collect all unique chords
    all_chords = set()
    for tab in tabs.values():
        all_chords.update(tab.get("chords", []))

    return {
        "total_tabs": len(tabs),
        "unique_artists": len(artists),
        "by_type": types,
        "with_lyrics": with_lyrics,
        "enriched": enriched,
        "unique_chords": len(all_chords),
        "built_at": index.get("built_at"),
    }


def find_tab_by_name(index: dict, song_name: str) -> dict | None:
    """
    Find a tab by song name (case-insensitive, partial match).

    Returns the first matching tab entry or None.
    """
    song_lower = song_name.lower()

    for tab in index.get("tabs", {}).values():
        tab_song = tab.get("song", "").lower()
        if song_lower in tab_song or tab_song in song_lower:
            return tab

    return None


def find_tab_by_artist_and_song(index: dict, artist: str, song: str) -> dict | None:
    """
    Find a tab by artist and song name (case-insensitive, partial match).
    """
    artist_lower = artist.lower()
    song_lower = song.lower()

    for tab in index.get("tabs", {}).values():
        tab_artist = tab.get("artist", "").lower()
        tab_song = tab.get("song", "").lower()

        if artist_lower in tab_artist and song_lower in tab_song:
            return tab

    return None


def list_artists(index: dict) -> list[str]:
    """Get a sorted list of all unique artists in the index."""
    artists = set()
    for tab in index.get("tabs", {}).values():
        artist = tab.get("artist")
        if artist:
            artists.add(artist)
    return sorted(artists)


def list_tabs_by_artist(index: dict, artist: str) -> list[dict]:
    """Get all tabs by a specific artist (case-insensitive partial match)."""
    artist_lower = artist.lower()
    results = []

    for tab in index.get("tabs", {}).values():
        tab_artist = tab.get("artist", "").lower()
        if artist_lower in tab_artist:
            results.append(tab)

    return sorted(results, key=lambda x: x.get("song", ""))
