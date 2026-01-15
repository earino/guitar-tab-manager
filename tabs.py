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
from lib import llm
from lib import medley as medley_lib


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


def cmd_enrich(args):
    """Enrich tabs with LLM-generated mood, themes, and tempo."""
    idx = ensure_index()

    # Check LMStudio availability
    try:
        client = llm.require_client()
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    print("LMStudio connected!")
    models = client.get_models()
    if models:
        print(f"Available models: {', '.join(models)}")

    # Find tabs that need enrichment
    tabs_to_enrich = []
    for file_path, tab in idx.get("tabs", {}).items():
        if not tab.get("mood"):  # Not yet enriched
            tabs_to_enrich.append((file_path, tab))

    if not tabs_to_enrich:
        print("\nAll tabs are already enriched!")
        return

    if args.limit:
        tabs_to_enrich = tabs_to_enrich[:args.limit]

    print(f"\nEnriching {len(tabs_to_enrich)} tabs...")

    enriched = 0
    failed = 0

    for i, (file_path, tab) in enumerate(tabs_to_enrich, 1):
        song = tab.get("song", "Unknown")
        artist = tab.get("artist", "Unknown")

        print(f"[{i}/{len(tabs_to_enrich)}] {artist} - {song}...", end=" ", flush=True)

        try:
            # Read tab content
            content = Path(file_path).read_text(encoding="utf-8")

            # Analyze with LLM
            analysis = client.analyze_tab(content, song, artist)

            # Update index entry
            tab["mood"] = analysis.get("mood", [])
            tab["themes"] = analysis.get("themes", [])
            tab["tempo_feel"] = analysis.get("tempo_feel", "medium")
            tab["description"] = analysis.get("description", "")

            print(f"mood={analysis['mood']}, themes={analysis['themes']}")
            enriched += 1

        except Exception as e:
            print(f"FAILED: {e}")
            failed += 1

    # Save updated index
    tab_index.save_index(idx, Path(config.INDEX_FILE))

    print(f"\nEnrichment complete!")
    print(f"  Enriched: {enriched}")
    print(f"  Failed: {failed}")


def cmd_search(args):
    """Semantic search using LLM (searches mood, themes, description)."""
    idx = ensure_index()

    query = args.query.lower()

    # First try mood/theme search on enriched data
    results = []

    for tab in idx.get("tabs", {}).values():
        score = 0

        # Check mood
        moods = tab.get("mood") or []
        for mood in moods:
            if query in mood.lower():
                score += 2

        # Check themes
        themes = tab.get("themes") or []
        for theme in themes:
            if query in theme.lower():
                score += 2

        # Check description
        description = tab.get("description") or ""
        if query in description.lower():
            score += 1

        # Check song/artist as fallback
        if query in tab.get("song", "").lower():
            score += 1
        if query in tab.get("artist", "").lower():
            score += 0.5

        if score > 0:
            results.append((tab, score))

    if not results:
        # Check if any tabs are enriched
        enriched_count = sum(1 for t in idx.get("tabs", {}).values() if t.get("mood"))
        if enriched_count == 0:
            print("No tabs have been enriched yet.")
            print("Run 'python tabs.py enrich' first to add mood/theme data.")
        else:
            print(f"No results found for: {args.query}")
        return

    # Sort by score
    results.sort(key=lambda x: x[1], reverse=True)

    print(f"\nSearch results for '{args.query}':\n")

    for i, (tab, score) in enumerate(results[:args.count], 1):
        mood_str = ", ".join(tab.get("mood", [])) or "N/A"
        themes_str = ", ".join(tab.get("themes", [])) or "N/A"
        print(f"  {i}. {search.format_result(tab)}")
        print(f"      Mood: {mood_str} | Themes: {themes_str}")
        if tab.get("description"):
            print(f"      {tab['description']}")


def cmd_mood(args):
    """Find tabs by mood."""
    idx = ensure_index()

    results = search.search_by_mood(idx, args.mood)

    if not results:
        print(f"No tabs found with mood: {args.mood}")
        print("\nAvailable moods in your collection:")
        moods = set()
        for tab in idx.get("tabs", {}).values():
            moods.update(tab.get("mood") or [])
        if moods:
            print(f"  {', '.join(sorted(moods))}")
        else:
            print("  (No tabs enriched yet - run 'python tabs.py enrich')")
        return

    print(f"\nTabs with mood '{args.mood}' ({len(results)} found):\n")
    for tab in sorted(results, key=lambda x: (x.get("artist", ""), x.get("song", ""))):
        print(f"  {search.format_result(tab)}")


def cmd_theme(args):
    """Find tabs by theme."""
    idx = ensure_index()

    results = search.search_by_theme(idx, args.theme)

    if not results:
        print(f"No tabs found with theme: {args.theme}")
        print("\nAvailable themes in your collection:")
        themes = set()
        for tab in idx.get("tabs", {}).values():
            themes.update(tab.get("themes") or [])
        if themes:
            print(f"  {', '.join(sorted(themes))}")
        else:
            print("  (No tabs enriched yet - run 'python tabs.py enrich')")
        return

    print(f"\nTabs with theme '{args.theme}' ({len(results)} found):\n")
    for tab in sorted(results, key=lambda x: (x.get("artist", ""), x.get("song", ""))):
        print(f"  {search.format_result(tab)}")


def cmd_medley(args):
    """Build a medley starting from a seed song."""
    idx = ensure_index()

    # Find the seed song
    seed = tab_index.find_tab_by_name(idx, args.song)

    if not seed:
        print(f"Song not found: {args.song}")
        print("\nTry searching with: python tabs.py find --song \"partial name\"")
        return

    print(f"\nBuilding medley starting from: {seed.get('artist')} - {seed.get('song')}")

    # Get all songs
    all_songs = list(idx.get("tabs", {}).values())

    # Build the medley
    medley = medley_lib.build_medley(
        start_song=seed,
        all_songs=all_songs,
        count=args.count,
        diverse=not args.same_artist,
        mood_filter=args.mood,
    )

    if len(medley) < 2:
        print("Could not build a medley (not enough compatible songs)")
        return

    # Display the medley
    print(f"\n{'='*60}")
    print(f"MEDLEY ({len(medley)} songs)")
    print(f"{'='*60}\n")

    print(medley_lib.format_medley(medley, show_transitions=True))

    # Show analysis
    stats = medley_lib.analyze_medley(medley)
    print(f"\n{'-'*60}")
    print("MEDLEY ANALYSIS")
    print(f"{'-'*60}")
    print(f"Unique artists: {stats['unique_artists']}")
    print(f"Total unique chords: {stats['total_unique_chords']}")
    print(f"Avg transition score: {stats['avg_transition_score']:.1%}")
    print(f"Keys: {' -> '.join(stats['keys'])}")


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

LLM-powered (requires LMStudio):
  enrich    Analyze tabs for mood, themes, tempo
  search    Semantic search by mood/theme
  mood      Find tabs by mood
  theme     Find tabs by theme

Medley building:
  medley    Build a medley from a seed song

Examples:
  python tabs.py list --artist "Pink Floyd"
  python tabs.py find --chord "Am,G,C" --type Chords
  python tabs.py chords "Wish You Were Here"
  python tabs.py similar "Hotel California" --count 10
  python tabs.py medley "Wish You Were Here" --count 6
  python tabs.py index --rebuild
  python tabs.py enrich --limit 10
  python tabs.py search "sad songs"
  python tabs.py mood melancholic
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

    # enrich command (LLM)
    p_enrich = subparsers.add_parser("enrich", help="Enrich tabs with mood/themes via LLM")
    p_enrich.add_argument("--limit", "-l", type=int, help="Limit number of tabs to enrich")
    p_enrich.set_defaults(func=cmd_enrich)

    # search command (semantic)
    p_search = subparsers.add_parser("search", help="Semantic search by mood/theme/description")
    p_search.add_argument("query", help="Search query (e.g., 'sad', 'love', 'upbeat')")
    p_search.add_argument("--count", "-n", type=int, default=10, help="Number of results")
    p_search.set_defaults(func=cmd_search)

    # mood command
    p_mood = subparsers.add_parser("mood", help="Find tabs by mood")
    p_mood.add_argument("mood", help="Mood to search for (e.g., 'melancholic', 'upbeat')")
    p_mood.set_defaults(func=cmd_mood)

    # theme command
    p_theme = subparsers.add_parser("theme", help="Find tabs by theme")
    p_theme.add_argument("theme", help="Theme to search for (e.g., 'love', 'loss', 'travel')")
    p_theme.set_defaults(func=cmd_theme)

    # medley command
    p_medley = subparsers.add_parser("medley", help="Build a medley from a seed song")
    p_medley.add_argument("song", help="Seed song to start the medley")
    p_medley.add_argument("--count", "-n", type=int, default=5, help="Number of songs")
    p_medley.add_argument("--mood", "-m", help="Filter by mood")
    p_medley.add_argument("--same-artist", action="store_true", help="Allow same artist")
    p_medley.set_defaults(func=cmd_medley)

    args = parser_main.parse_args()

    if not args.command:
        parser_main.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
