#!/usr/bin/env python3
"""
Guitar Tab Exploration Tool

Search, explore, and build setlists from your guitar tab collection.
Uses comprehensive similarity scoring (key, chords, mood, themes, lyrics).

Usage:
    python tabs.py list [--artist X]
    python tabs.py find --artist "Beatles" --chord "Am"
    python tabs.py similar "Hotel California" --by all|chords|embeddings
    python tabs.py medley "Wish You Were Here" --count 6
    python tabs.py enrich --limit 10  # add mood/themes (requires LMStudio)
    python tabs.py embed --limit 10   # generate lyric embeddings (requires LMStudio)
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
from lib import embeddings as emb_lib
from lib import visualize as viz_lib


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
    """Find songs similar to a seed song using multiple signals."""
    idx = ensure_index()

    # Find the target tab
    tab = tab_index.find_tab_by_name(idx, args.song)

    if not tab:
        print(f"Tab not found: {args.song}")
        return

    print(f"\nFinding songs similar to: {tab.get('artist')} - {tab.get('song')}")

    # Determine similarity method
    method = args.by if hasattr(args, 'by') and args.by else "all"

    if method == "chords":
        print(f"(Based on chord similarity)\n")
        similar = search.chord_similarity(idx, tab, top_k=args.count)
        for i, (sim_tab, score) in enumerate(similar, 1):
            pct = int(score * 100)
            print(f"  {i}. {search.format_result(sim_tab)} - {pct}% chord overlap")
        return

    # For "all" or "embeddings", use comprehensive scoring
    embeddings_data = emb_lib.load_embeddings()
    has_embeddings = embeddings_data.get("embeddings") is not None and len(embeddings_data.get("file_paths", [])) > 0

    if method == "embeddings":
        if not has_embeddings:
            print("No embeddings found. Run 'python tabs.py embed' first.")
            return
        print(f"(Based on lyrical/thematic similarity via embeddings)\n")
        # Use embedding similarity directly
        target_emb = emb_lib.get_embedding_for_tab(tab, embeddings_data)
        if target_emb is None:
            print(f"No embedding found for this song. Run 'python tabs.py embed' to generate.")
            return
        similar_paths = emb_lib.find_similar_by_embedding(
            target_emb,
            embeddings_data["embeddings"],
            embeddings_data["file_paths"],
            top_k=args.count,
            exclude_path=tab.get("file_path"),
        )
        # Map paths back to tabs
        tabs_dict = idx.get("tabs", {})
        for i, (path, score) in enumerate(similar_paths, 1):
            sim_tab = tabs_dict.get(path)
            if sim_tab:
                pct = int(score * 100)
                themes = ", ".join((sim_tab.get("themes") or [])[:2]) or "N/A"
                print(f"  {i}. {search.format_result(sim_tab)} - {pct}% similar")
                print(f"      Themes: {themes}")
        return

    # "all" - comprehensive similarity using medley scoring
    print(f"(Comprehensive: key + chords + mood + themes" + (" + lyrics" if has_embeddings else "") + ")\n")
    if has_embeddings:
        print(f"Using embeddings for lyrical similarity ({len(embeddings_data['file_paths'])} songs)\n")
    else:
        print("Tip: Run 'python tabs.py embed' to include lyrical similarity\n")

    all_songs = list(idx.get("tabs", {}).values())
    scored = medley_lib.find_best_next(
        tab,
        all_songs,
        exclude_artists=None,  # Don't exclude artists for similarity search
        embeddings_data=embeddings_data if has_embeddings else None,
    )

    if not scored:
        print("No similar songs found.")
        return

    for i, (sim_tab, score) in enumerate(scored[:args.count], 1):
        pct = int(score * 100)
        details = []
        if sim_tab.get("key"):
            details.append(f"Key: {sim_tab['key']}")
        if sim_tab.get("mood"):
            details.append(f"Mood: {', '.join(sim_tab['mood'][:2])}")
        if sim_tab.get("themes"):
            details.append(f"Themes: {', '.join(sim_tab['themes'][:2])}")
        print(f"  {i}. {search.format_result(sim_tab)} - {pct}% match")
        if details:
            print(f"      {' | '.join(details)}")


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


def cmd_embed(args):
    """Generate embeddings for all tabs (for lyrical/thematic similarity)."""
    import numpy as np

    idx = ensure_index()

    # Check LMStudio availability
    try:
        client = llm.require_client()
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    print("LMStudio connected!")

    # Find embedding model
    embed_model = client.get_embedding_model()
    if not embed_model:
        print("Error: No embedding model found in LMStudio.")
        print("Load an embedding model like 'text-embedding-nomic-embed-text-v1.5'")
        return
    print(f"Using embedding model: {embed_model}")

    # Load existing embeddings
    existing = emb_lib.load_embeddings()
    existing_paths = set(existing.get("file_paths", []))

    # Find tabs that need embeddings
    tabs_to_embed = []
    for file_path, tab in idx.get("tabs", {}).items():
        if file_path not in existing_paths:
            tabs_to_embed.append((file_path, tab))

    if not tabs_to_embed:
        print("\nAll tabs already have embeddings!")
        return

    if args.limit:
        tabs_to_embed = tabs_to_embed[:args.limit]

    print(f"\nGenerating embeddings for {len(tabs_to_embed)} tabs...")

    new_paths = []
    new_embeddings = []
    failed = 0

    for i, (file_path, tab) in enumerate(tabs_to_embed, 1):
        song = tab.get("song", "Unknown")
        artist = tab.get("artist", "Unknown")

        print(f"[{i}/{len(tabs_to_embed)}] {artist} - {song}...", end=" ", flush=True)

        try:
            # Read tab content
            content = Path(file_path).read_text(encoding="utf-8")

            # Create embedding text
            embed_text = emb_lib.get_embedding_text(tab, content)

            # Generate embedding
            embedding = client.embed(embed_text)

            new_paths.append(file_path)
            new_embeddings.append(embedding)
            print("OK")

        except Exception as e:
            print(f"FAILED: {e}")
            failed += 1

    # Combine with existing embeddings
    if existing.get("embeddings") is not None and len(existing["file_paths"]) > 0:
        all_paths = list(existing["file_paths"]) + new_paths
        all_embeddings = np.vstack([existing["embeddings"], np.array(new_embeddings)])
    else:
        all_paths = new_paths
        all_embeddings = np.array(new_embeddings) if new_embeddings else np.array([])

    # Save embeddings
    if len(all_paths) > 0:
        emb_lib.save_embeddings(all_paths, all_embeddings)
        print(f"\nEmbeddings saved to {config.EMBEDDINGS_FILE}")

    print(f"\nEmbedding generation complete!")
    print(f"  Generated: {len(new_embeddings)}")
    print(f"  Failed: {failed}")
    print(f"  Total: {len(all_paths)}")


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

    # Load embeddings for lyrical/thematic coherence
    embeddings_data = emb_lib.load_embeddings()
    has_embeddings = embeddings_data.get("embeddings") is not None and len(embeddings_data.get("file_paths", [])) > 0

    if has_embeddings:
        print(f"Using embeddings for thematic coherence ({len(embeddings_data['file_paths'])} songs)")
    else:
        print("No embeddings found - run 'python tabs.py embed' for better narrative flow")

    # Get all songs
    all_songs = list(idx.get("tabs", {}).values())

    # Build the medley
    medley = medley_lib.build_medley(
        start_song=seed,
        all_songs=all_songs,
        count=args.count,
        diverse=not args.same_artist,
        mood_filter=args.mood,
        embeddings_data=embeddings_data if has_embeddings else None,
    )

    if len(medley) < 2:
        print("Could not build a medley (not enough compatible songs)")
        return

    # Generate combined tabs if requested
    if args.tabs:
        output = medley_lib.generate_medley_tabs(
            medley,
            embeddings_data=embeddings_data if has_embeddings else None,
        )
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(output, encoding="utf-8")
            print(f"\nMedley tabs written to: {output_path}")
        else:
            print("\n" + output)
        return

    # Display the medley summary
    print(f"\n{'='*60}")
    print(f"MEDLEY ({len(medley)} songs)")
    print(f"{'='*60}\n")

    print(medley_lib.format_medley(medley, show_transitions=True, embeddings_data=embeddings_data if has_embeddings else None))

    # Show analysis
    stats = medley_lib.analyze_medley(medley, embeddings_data if has_embeddings else None)
    print(f"\n{'-'*60}")
    print("MEDLEY ANALYSIS")
    print(f"{'-'*60}")
    print(f"Unique artists: {stats['unique_artists']}")
    print(f"Total unique chords: {stats['total_unique_chords']}")
    print(f"Avg transition score: {stats['avg_transition_score']:.1%}")
    if has_embeddings and stats.get('thematic_coherence'):
        print(f"Thematic coherence: {stats['thematic_coherence']:.1%}")
    if stats.get('themes_covered'):
        print(f"Themes: {', '.join(stats['themes_covered'][:5])}")
    print(f"Keys: {' -> '.join(stats['keys'])}")

    print(f"\nTip: Use --tabs to output the full combined tab sheet")


MOOD_CATEGORIES = ["sad", "nostalgic", "hopeful", "romantic", "playful", "intense", "peaceful"]


def cmd_classify_moods(args):
    """Classify moods into semantic categories using LLM."""
    import json as json_module

    idx = ensure_index()

    # Extract all unique moods
    all_moods = set()
    for tab in idx.get("tabs", {}).values():
        moods = tab.get("mood") or []
        all_moods.update(moods)

    if not all_moods:
        print("No moods found. Run 'python tabs.py enrich' first.")
        return

    print(f"Found {len(all_moods)} unique moods to classify")
    print(f"Target categories: {', '.join(MOOD_CATEGORIES)}")

    # Check LMStudio availability
    try:
        client = llm.require_client()
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    print("\nLMStudio connected! Classifying moods...")

    # Classify all moods
    mood_list = sorted(all_moods)
    mapping = client.classify_moods(mood_list, MOOD_CATEGORIES)

    # Save mapping
    output_path = Path("mood_categories.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json_module.dump(mapping, f, indent=2, sort_keys=True)

    print(f"\nMapping saved to: {output_path}")

    # Show summary
    category_counts = {}
    for mood, category in mapping.items():
        category_counts[category] = category_counts.get(category, 0) + 1

    print("\nCategory distribution:")
    for cat in MOOD_CATEGORIES:
        count = category_counts.get(cat, 0)
        print(f"  {cat}: {count} moods")

    # Show some examples
    print("\nSample mappings:")
    for mood, category in list(mapping.items())[:10]:
        print(f"  {mood} -> {category}")


def cmd_visualize(args):
    """Generate interactive 2D/3D visualization of song embeddings."""
    idx = ensure_index()

    # Load embeddings
    embeddings_data = emb_lib.load_embeddings()

    if embeddings_data.get("embeddings") is None or len(embeddings_data.get("file_paths", [])) == 0:
        print("No embeddings found. Run 'python tabs.py embed' first.")
        return

    embeddings = embeddings_data["embeddings"]
    file_paths = embeddings_data["file_paths"]

    print(f"Loaded {len(file_paths)} song embeddings")
    print(f"Embedding dimensions: {embeddings.shape[1]}")

    # Match embeddings to tab metadata
    tabs_dict = idx.get("tabs", {})
    tabs = []
    valid_indices = []

    for i, path in enumerate(file_paths):
        if path in tabs_dict:
            tabs.append(tabs_dict[path])
            valid_indices.append(i)

    if not tabs:
        print("Could not match embeddings to tab metadata.")
        return

    # Filter embeddings to valid ones
    embeddings = embeddings[valid_indices]
    print(f"Matched {len(tabs)} songs with metadata")

    # Reduce dimensions
    n_components = 3 if args.three_d else 2
    method = args.method

    print(f"\nReducing dimensions using {method.upper()} to {n_components}D...")
    reduced = viz_lib.reduce_dimensions(
        embeddings,
        method=method,
        n_components=n_components,
    )
    print("Dimension reduction complete!")

    # Create visualization
    print(f"Creating visualization (colored by {args.color})...")
    fig = viz_lib.create_visualization(
        reduced,
        tabs,
        color_by=args.color,
        dim=n_components,
    )

    # Save to HTML
    output_path = Path(args.output)
    viz_lib.save_html(fig, output_path)

    print(f"\nVisualization saved to: {output_path}")
    print(f"Open in your browser to explore your song collection!")
    print(f"\nTip: Try different color options with --color (mood, key, artist, theme, type)")


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
  similar   Find similar songs (by all signals, chords, or embeddings)
  index     Build or show index statistics

LLM-powered (requires LMStudio):
  enrich    Analyze tabs for mood, themes, tempo
  embed     Generate embeddings for lyrical/thematic similarity
  search    Semantic search by mood/theme
  mood      Find tabs by mood
  theme     Find tabs by theme

Medley building:
  medley    Build a medley from a seed song (uses all signals)
            Use --tabs to output combined tab sheet

Visualization:
  visualize Interactive 2D/3D visualization of song embeddings
            Color by mood, key, artist, or theme

Examples:
  python tabs.py list --artist "Pink Floyd"
  python tabs.py find --chord "Am,G,C" --type Chords
  python tabs.py chords "Wish You Were Here"
  python tabs.py similar "Hotel California"              # comprehensive
  python tabs.py similar "Hotel California" --by chords  # chords only
  python tabs.py similar "Hotel California" --by embeddings  # lyrics only
  python tabs.py medley "Wish You Were Here" --count 6   # summary only
  python tabs.py medley "Wish You Were Here" --tabs      # full tab sheet
  python tabs.py medley "Wish You Were Here" --tabs -o medley.txt  # save to file
  python tabs.py index --rebuild
  python tabs.py enrich --limit 10
  python tabs.py embed --limit 10
  python tabs.py search "sad songs"
  python tabs.py mood melancholic
  python tabs.py visualize                         # 2D visualization
  python tabs.py visualize --3d --color key        # 3D, colored by key
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
    p_similar.add_argument("--by", "-b", choices=["all", "chords", "embeddings"], default="all",
                          help="Similarity method: all (comprehensive), chords, or embeddings")
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

    # embed command (LLM)
    p_embed = subparsers.add_parser("embed", help="Generate embeddings for lyrical/thematic similarity")
    p_embed.add_argument("--limit", "-l", type=int, help="Limit number of tabs to embed")
    p_embed.set_defaults(func=cmd_embed)

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
    p_medley.add_argument("--tabs", "-t", action="store_true",
                          help="Output full combined tab sheet (not just summary)")
    p_medley.add_argument("--output", "-o", help="Write tabs to file instead of stdout")
    p_medley.set_defaults(func=cmd_medley)

    # classify-moods command
    p_classify = subparsers.add_parser("classify-moods", help="Classify moods into semantic categories via LLM")
    p_classify.set_defaults(func=cmd_classify_moods)

    # visualize command
    p_viz = subparsers.add_parser("visualize", help="Interactive 2D/3D visualization of song embeddings")
    p_viz.add_argument("--3d", dest="three_d", action="store_true",
                       help="Generate 3D visualization (default: 2D)")
    p_viz.add_argument("--color", "-c", default="mood",
                       choices=["mood", "key", "artist", "theme", "type"],
                       help="Attribute to color points by (default: mood)")
    p_viz.add_argument("--method", "-m", default="tsne",
                       choices=["tsne", "pca"],
                       help="Dimensionality reduction method (default: tsne)")
    p_viz.add_argument("--output", "-o", default="song_visualization.html",
                       help="Output HTML file (default: song_visualization.html)")
    p_viz.set_defaults(func=cmd_visualize)

    args = parser_main.parse_args()

    if not args.command:
        parser_main.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
