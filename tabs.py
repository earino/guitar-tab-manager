#!/usr/bin/env python3
"""
Guitar Tab Exploration Tool

Search, explore, and build setlists from your guitar tab collection.

Usage:
    python tabs.py list [--artist X]
    python tabs.py find --artist "Beatles" --chord "Am"
    python tabs.py chords "Hotel California"
    python tabs.py index [--rebuild]
"""

import argparse
import sys
from pathlib import Path

import config
from lib import index as tab_index
from lib import search
from lib import parser


def ensure_index(rebuild: bool = False) -> dict:
    """Load the index, building it if necessary."""
    index_path = Path(config.INDEX_FILE)
    tabs_dir = Path(config.OUTPUT_DIR)

    if not tabs_dir.exists():
        print(f"Error: Tabs directory not found: {tabs_dir}")
        print("Run backup_tabs.py first to download your tabs.")
        sys.exit(1)

    if rebuild or not index_path.exists():
        print("Building index..." if not rebuild else "Rebuilding index...")
        idx = tab_index.build_index(tabs_dir, verbose=True)
        tab_index.save_index(idx, index_path)
        print(f"Index saved to {index_path}")
        return idx

    return tab_index.load_index(index_path)


def cmd_list(args):
    """List tabs, optionally filtered by artist."""
    idx = ensure_index()

    if args.artist:
        tabs = tab_index.list_tabs_by_artist(idx, args.artist)
        if not tabs:
            print(f"No tabs found for artist: {args.artist}")
            return
        print(f"\nTabs by '{args.artist}' ({len(tabs)} found):\n")
    else:
        tabs = list(idx.get("tabs", {}).values())
        print(f"\nAll tabs ({len(tabs)} total):\n")

    # Sort by artist, then song
    tabs = sorted(tabs, key=lambda x: (x.get("artist", ""), x.get("song", "")))

    for tab in tabs:
        print(f"  {search.format_result(tab)}")

    if not args.artist:
        print(f"\nUse --artist to filter by artist")


def cmd_artists(args):
    """List all artists in the collection."""
    idx = ensure_index()
    artists = tab_index.list_artists(idx)

    print(f"\nArtists ({len(artists)} total):\n")
    for artist in artists:
        tabs = tab_index.list_tabs_by_artist(idx, artist)
        print(f"  {artist} ({len(tabs)} tabs)")


def cmd_find(args):
    """Find tabs matching criteria."""
    idx = ensure_index()

    # Parse chord list if provided
    chords = None
    if args.chord:
        chords = [c.strip() for c in args.chord.split(",")]

    results = search.filter_search(
        idx,
        artist=args.artist,
        song=args.song,
        tab_type=args.type,
        chords=chords,
        key=args.key,
    )

    if not results:
        print("No tabs found matching your criteria.")
        return

    print(f"\nFound {len(results)} matching tab(s):\n")
    for tab in sorted(results, key=lambda x: (x.get("artist", ""), x.get("song", ""))):
        print(f"  {search.format_result(tab, show_chords=args.show_chords)}")


def cmd_chords(args):
    """Show chords for a specific song."""
    idx = ensure_index()

    # Find the tab
    tab = tab_index.find_tab_by_name(idx, args.song)

    if not tab:
        print(f"Tab not found: {args.song}")
        print("\nTry searching with: python tabs.py find --song \"partial name\"")
        return

    print(f"\n{tab.get('artist', 'Unknown')} - {tab.get('song', 'Unknown')}")
    print(f"Type: {tab.get('type', 'Unknown')}")

    if tab.get("key"):
        print(f"Key: {tab['key']}")
    if tab.get("capo"):
        print(f"Capo: {tab['capo']}")

    chords = tab.get("chords", [])
    if chords:
        print(f"\nChords ({len(chords)}):")
        print(f"  {', '.join(chords)}")
    else:
        print("\nNo chords extracted.")

    sections = tab.get("sections", [])
    if sections:
        print(f"\nSections: {', '.join(sections)}")

    print(f"\nFile: {tab.get('file_path')}")


def cmd_similar(args):
    """Find songs with similar chords."""
    idx = ensure_index()

    # Find the target tab
    tab = tab_index.find_tab_by_name(idx, args.song)

    if not tab:
        print(f"Tab not found: {args.song}")
        return

    print(f"\nFinding songs similar to: {tab.get('artist')} - {tab.get('song')}")
    print(f"(Based on chord similarity)\n")

    similar = search.chord_similarity(idx, tab, top_k=args.count)

    if not similar:
        print("No similar songs found.")
        return

    for i, (sim_tab, score) in enumerate(similar, 1):
        pct = int(score * 100)
        print(f"  {i}. {search.format_result(sim_tab)} - {pct}% chord overlap")


def cmd_index(args):
    """Build or rebuild the index."""
    idx = ensure_index(rebuild=args.rebuild)
    stats = tab_index.get_stats(idx)

    print(f"\n{'='*50}")
    print("INDEX STATISTICS")
    print(f"{'='*50}")
    print(f"Total tabs:      {stats['total_tabs']}")
    print(f"Unique artists:  {stats['unique_artists']}")
    print(f"With lyrics:     {stats['with_lyrics']}")
    print(f"Unique chords:   {stats['unique_chords']}")
    print(f"LLM enriched:    {stats['enriched']}")
    print(f"{'='*50}")

    print("\nBy type:")
    for tab_type, count in sorted(stats['by_type'].items(), key=lambda x: -x[1]):
        print(f"  {tab_type}: {count}")

    print(f"\nBuilt at: {stats.get('built_at', 'Unknown')}")


def cmd_stats(args):
    """Show collection statistics."""
    cmd_index(args)


def main():
    parser_main = argparse.ArgumentParser(
        description="Guitar Tab Exploration Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  list      List all tabs or filter by artist
  artists   List all artists in the collection
  find      Find tabs by criteria (artist, song, chord, key, type)
  chords    Show chords for a specific song
  similar   Find songs with similar chord progressions
  index     Build or show index statistics

Examples:
  python tabs.py list --artist "Pink Floyd"
  python tabs.py find --chord "Am,G,C" --type Chords
  python tabs.py chords "Wish You Were Here"
  python tabs.py similar "Hotel California" --count 10
  python tabs.py index --rebuild
        """,
    )

    subparsers = parser_main.add_subparsers(dest="command", help="Command to run")

    # list command
    p_list = subparsers.add_parser("list", help="List tabs")
    p_list.add_argument("--artist", "-a", help="Filter by artist name")
    p_list.set_defaults(func=cmd_list)

    # artists command
    p_artists = subparsers.add_parser("artists", help="List all artists")
    p_artists.set_defaults(func=cmd_artists)

    # find command
    p_find = subparsers.add_parser("find", help="Find tabs by criteria")
    p_find.add_argument("--artist", "-a", help="Filter by artist")
    p_find.add_argument("--song", "-s", help="Filter by song name")
    p_find.add_argument("--chord", "-c", help="Filter by chords (comma-separated)")
    p_find.add_argument("--key", "-k", help="Filter by key (e.g., Am, G)")
    p_find.add_argument("--type", "-t", help="Filter by type (Chords, Tab, etc.)")
    p_find.add_argument("--show-chords", action="store_true", help="Show chords in results")
    p_find.set_defaults(func=cmd_find)

    # chords command
    p_chords = subparsers.add_parser("chords", help="Show chords for a song")
    p_chords.add_argument("song", help="Song name to look up")
    p_chords.set_defaults(func=cmd_chords)

    # similar command
    p_similar = subparsers.add_parser("similar", help="Find similar songs")
    p_similar.add_argument("song", help="Song to find similar matches for")
    p_similar.add_argument("--count", "-n", type=int, default=10, help="Number of results")
    p_similar.set_defaults(func=cmd_similar)

    # index command
    p_index = subparsers.add_parser("index", help="Build or show index")
    p_index.add_argument("--rebuild", "-r", action="store_true", help="Force rebuild")
    p_index.set_defaults(func=cmd_index)

    # stats command (alias for index)
    p_stats = subparsers.add_parser("stats", help="Show collection statistics")
    p_stats.add_argument("--rebuild", "-r", action="store_true", help="Force rebuild")
    p_stats.set_defaults(func=cmd_stats)

    args = parser_main.parse_args()

    if not args.command:
        parser_main.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
