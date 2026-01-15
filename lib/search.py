"""
Search implementations for guitar tabs.
"""

from pathlib import Path


def text_search(index: dict, query: str, field: str = None) -> list[dict]:
    """
    Search tabs by text query.

    Args:
        index: The tab index
        query: Search query (case-insensitive)
        field: Optional field to search in ('song', 'artist', 'content').
               If None, searches song and artist.

    Returns a list of matching tab entries.
    """
    query_lower = query.lower()
    results = []

    for tab in index.get("tabs", {}).values():
        matched = False

        if field == "song":
            if query_lower in tab.get("song", "").lower():
                matched = True
        elif field == "artist":
            if query_lower in tab.get("artist", "").lower():
                matched = True
        elif field == "content":
            # Need to read the actual file for content search
            file_path = Path(tab.get("file_path", ""))
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8").lower()
                if query_lower in content:
                    matched = True
        else:
            # Search both song and artist
            if (query_lower in tab.get("song", "").lower() or
                query_lower in tab.get("artist", "").lower()):
                matched = True

        if matched:
            results.append(tab)

    return results


def filter_search(
    index: dict,
    artist: str = None,
    song: str = None,
    tab_type: str = None,
    chords: list[str] = None,
    key: str = None,
    has_lyrics: bool = None,
    capo: int = None,
) -> list[dict]:
    """
    Filter tabs by multiple criteria.

    All provided criteria must match (AND logic).
    """
    results = []

    for tab in index.get("tabs", {}).values():
        # Check each criterion
        if artist:
            if artist.lower() not in tab.get("artist", "").lower():
                continue

        if song:
            if song.lower() not in tab.get("song", "").lower():
                continue

        if tab_type:
            if tab_type.lower() != tab.get("type", "").lower():
                continue

        if chords:
            tab_chords = set(c.lower() for c in tab.get("chords", []))
            required_chords = set(c.lower() for c in chords)
            if not required_chords.issubset(tab_chords):
                continue

        if key:
            if key.lower() != (tab.get("key") or "").lower():
                continue

        if has_lyrics is not None:
            if tab.get("has_lyrics") != has_lyrics:
                continue

        if capo is not None:
            if tab.get("capo") != capo:
                continue

        results.append(tab)

    return results


def chord_similarity(index: dict, target_tab: dict, top_k: int = 10) -> list[tuple[dict, float]]:
    """
    Find tabs with similar chord progressions using Jaccard similarity.

    Args:
        index: The tab index
        target_tab: The tab to find similar songs for
        top_k: Number of results to return

    Returns list of (tab, similarity_score) tuples, sorted by similarity.
    """
    target_chords = set(target_tab.get("chords", []))

    if not target_chords:
        return []

    similarities = []

    for tab in index.get("tabs", {}).values():
        # Skip the target tab itself
        if tab.get("file_path") == target_tab.get("file_path"):
            continue

        tab_chords = set(tab.get("chords", []))

        if not tab_chords:
            continue

        # Jaccard similarity: intersection / union
        intersection = len(target_chords & tab_chords)
        union = len(target_chords | tab_chords)

        if union > 0:
            similarity = intersection / union
            similarities.append((tab, similarity))

    # Sort by similarity (descending)
    similarities.sort(key=lambda x: x[1], reverse=True)

    return similarities[:top_k]


def search_by_chords(index: dict, chords: list[str], match_all: bool = True) -> list[dict]:
    """
    Find tabs that contain specific chords.

    Args:
        index: The tab index
        chords: List of chord names to search for
        match_all: If True, tab must contain ALL chords. If False, ANY chord.

    Returns list of matching tabs.
    """
    search_chords = set(c.lower() for c in chords)
    results = []

    for tab in index.get("tabs", {}).values():
        tab_chords = set(c.lower() for c in tab.get("chords", []))

        if match_all:
            if search_chords.issubset(tab_chords):
                results.append(tab)
        else:
            if search_chords & tab_chords:  # Any overlap
                results.append(tab)

    return results


def search_by_mood(index: dict, mood: str) -> list[dict]:
    """
    Find tabs with a specific mood (requires LLM enrichment).
    """
    mood_lower = mood.lower()
    results = []

    for tab in index.get("tabs", {}).values():
        tab_moods = tab.get("mood") or []
        if any(mood_lower in m.lower() for m in tab_moods):
            results.append(tab)

    return results


def search_by_theme(index: dict, theme: str) -> list[dict]:
    """
    Find tabs with a specific theme (requires LLM enrichment).
    """
    theme_lower = theme.lower()
    results = []

    for tab in index.get("tabs", {}).values():
        tab_themes = tab.get("themes") or []
        if any(theme_lower in t.lower() for t in tab_themes):
            results.append(tab)

    return results


def format_result(tab: dict, show_chords: bool = False) -> str:
    """Format a tab entry for display."""
    artist = tab.get("artist", "Unknown")
    song = tab.get("song", "Unknown")
    tab_type = tab.get("type", "")
    key = tab.get("key", "")

    line = f"{artist} - {song}"

    if tab_type:
        line += f" ({tab_type})"

    if key:
        line += f" [Key: {key}]"

    if tab.get("capo"):
        line += f" [Capo: {tab['capo']}]"

    if show_chords and tab.get("chords"):
        chords_str = ", ".join(tab["chords"][:8])
        if len(tab["chords"]) > 8:
            chords_str += "..."
        line += f"\n    Chords: {chords_str}"

    return line
