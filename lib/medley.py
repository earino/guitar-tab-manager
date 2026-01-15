"""
Medley building logic for creating song sequences.

Uses multiple signals for coherent medleys:
- Key compatibility (music theory)
- Chord overlap (playing ease)
- Mood similarity (emotional arc)
- Lyrical/thematic similarity via embeddings (narrative coherence)
"""

from . import music
from . import embeddings as emb_lib


def score_transition(
    song_a: dict,
    song_b: dict,
    embeddings_data: dict = None,
) -> float:
    """
    Score how well song_b follows song_a in a medley.

    Returns a score from 0.0 to 1.0 where higher is better.

    Factors (with embeddings available):
    - Key compatibility (30%)
    - Chord overlap (25%)
    - Mood similarity (15%)
    - Lyrical/thematic embeddings (25%)
    - Type match (5%)

    Without embeddings, mood gets extra weight.
    """
    score = 0.0
    has_embeddings = embeddings_data is not None and embeddings_data.get("embeddings") is not None

    # Key compatibility (30%)
    key_a = song_a.get("key")
    key_b = song_b.get("key")
    capo_a = song_a.get("capo") or 0
    capo_b = song_b.get("capo") or 0

    eff_key_a = music.effective_key(key_a, capo_a) if key_a else None
    eff_key_b = music.effective_key(key_b, capo_b) if key_b else None

    key_score = music.key_compatibility_score(eff_key_a, eff_key_b)
    score += 0.30 * key_score

    # Chord overlap (25%)
    chords_a = song_a.get("chords", [])
    chords_b = song_b.get("chords", [])
    chord_score = music.chord_overlap_score(chords_a, chords_b)
    score += 0.25 * chord_score

    # Mood similarity (15% with embeddings, 25% without)
    moods_a = set(song_a.get("mood") or [])
    moods_b = set(song_b.get("mood") or [])

    mood_weight = 0.15 if has_embeddings else 0.25

    if moods_a and moods_b:
        mood_overlap = len(moods_a & moods_b) / len(moods_a | moods_b)
        score += mood_weight * mood_overlap
    else:
        score += mood_weight * 0.5  # Neutral if no mood data

    # Lyrical/thematic similarity via embeddings (25%)
    if has_embeddings:
        emb_score = emb_lib.embedding_similarity_score(song_a, song_b, embeddings_data)
        score += 0.25 * emb_score
    else:
        # Without embeddings, distribute weight to themes if available
        themes_a = set(song_a.get("themes") or [])
        themes_b = set(song_b.get("themes") or [])
        if themes_a and themes_b:
            theme_overlap = len(themes_a & themes_b) / len(themes_a | themes_b)
            score += 0.15 * theme_overlap
        else:
            score += 0.075  # Neutral

    # Type match (5%)
    type_a = song_a.get("type", "")
    type_b = song_b.get("type", "")
    if type_a and type_b and type_a == type_b:
        score += 0.05
    else:
        score += 0.025

    return score


def find_best_next(
    current: dict,
    candidates: list[dict],
    exclude_artists: set[str] = None,
    embeddings_data: dict = None,
) -> list[tuple[dict, float]]:
    """
    Find the best next songs to follow the current song.

    Args:
        current: The current song
        candidates: List of candidate songs
        exclude_artists: Artists to exclude (for variety)
        embeddings_data: Embeddings for lyrical similarity

    Returns list of (song, score) tuples sorted by score (descending).
    """
    scored = []

    for candidate in candidates:
        # Skip same song
        if candidate.get("file_path") == current.get("file_path"):
            continue

        # Skip excluded artists
        if exclude_artists and candidate.get("artist") in exclude_artists:
            continue

        score = score_transition(current, candidate, embeddings_data)
        scored.append((candidate, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def build_medley(
    start_song: dict,
    all_songs: list[dict],
    count: int = 5,
    diverse: bool = True,
    mood_filter: str = None,
    embeddings_data: dict = None,
) -> list[dict]:
    """
    Build a medley starting from a seed song.

    Args:
        start_song: The song to start with
        all_songs: All available songs
        count: Number of songs in the medley
        diverse: If True, avoid repeating artists
        mood_filter: Only include songs with this mood
        embeddings_data: Embeddings for lyrical/thematic coherence

    Returns ordered list of songs for the medley.
    """
    medley = [start_song]
    used_paths = {start_song.get("file_path")}
    used_artists = {start_song.get("artist")} if diverse else set()

    # Filter candidates by mood if specified
    candidates = all_songs
    if mood_filter:
        mood_lower = mood_filter.lower()
        candidates = [
            s for s in all_songs
            if any(mood_lower in m.lower() for m in (s.get("mood") or []))
        ]

    while len(medley) < count:
        current = medley[-1]

        # Find candidates (exclude already used)
        available = [
            s for s in candidates
            if s.get("file_path") not in used_paths
        ]

        if not available:
            break

        # Find best next song
        scored = find_best_next(
            current,
            available,
            exclude_artists=used_artists if diverse else None,
            embeddings_data=embeddings_data,
        )

        if not scored:
            # If no matches with artist exclusion, try without
            if diverse:
                scored = find_best_next(current, available, embeddings_data=embeddings_data)

        if not scored:
            break

        # Pick the best
        best_song, _ = scored[0]
        medley.append(best_song)
        used_paths.add(best_song.get("file_path"))
        if diverse:
            used_artists.add(best_song.get("artist"))

    return medley


def suggest_transition(
    song_a: dict,
    song_b: dict,
    embeddings_data: dict = None,
) -> str:
    """
    Generate a transition suggestion between two songs.
    """
    suggestions = []

    key_a = song_a.get("key")
    key_b = song_b.get("key")
    capo_a = song_a.get("capo")
    capo_b = song_b.get("capo")

    # Key transition
    if key_a and key_b:
        if key_a == key_b:
            suggestions.append(f"Same key ({key_a})")
        elif music.are_keys_compatible(key_a, key_b):
            suggestions.append(f"Keys: {key_a} -> {key_b}")
        else:
            suggestions.append(f"Key change: {key_a} -> {key_b}")

    # Capo change
    if capo_a != capo_b:
        if capo_a and capo_b:
            suggestions.append(f"Capo: {capo_a} -> {capo_b}")
        elif capo_b:
            suggestions.append(f"Add capo {capo_b}")
        elif capo_a:
            suggestions.append(f"Remove capo")

    # Thematic connection
    themes_a = set(song_a.get("themes") or [])
    themes_b = set(song_b.get("themes") or [])
    common_themes = themes_a & themes_b
    if common_themes:
        suggestions.append(f"Theme: {', '.join(list(common_themes)[:2])}")

    # Lyrical similarity note
    if embeddings_data and embeddings_data.get("embeddings") is not None:
        emb_score = emb_lib.embedding_similarity_score(song_a, song_b, embeddings_data)
        if emb_score > 0.7:
            suggestions.append("Strong lyrical connection")
        elif emb_score > 0.55:
            suggestions.append("Similar themes")

    return " | ".join(suggestions) if suggestions else "Transition"


def format_medley(
    medley: list[dict],
    show_transitions: bool = True,
    embeddings_data: dict = None,
) -> str:
    """Format a medley for display."""
    lines = []

    for i, song in enumerate(medley, 1):
        artist = song.get("artist", "Unknown")
        title = song.get("song", "Unknown")
        key = song.get("key", "?")
        capo = song.get("capo")

        line = f"{i}. {artist} - {title}"
        details = [f"Key: {key}"]
        if capo:
            details.append(f"Capo: {capo}")

        # Add themes if available
        themes = song.get("themes")
        if themes:
            details.append(f"Themes: {', '.join(themes[:2])}")

        line += f" [{', '.join(details)}]"
        lines.append(line)

        # Add transition suggestion
        if show_transitions and i < len(medley):
            next_song = medley[i]
            transition = suggest_transition(song, next_song, embeddings_data)
            lines.append(f"   -> {transition}")

    return "\n".join(lines)


def analyze_medley(medley: list[dict], embeddings_data: dict = None) -> dict:
    """Analyze a medley and return statistics."""
    if not medley:
        return {}

    keys = [s.get("key") for s in medley if s.get("key")]
    artists = set(s.get("artist") for s in medley)
    all_chords = set()
    all_themes = set()
    for s in medley:
        all_chords.update(s.get("chords", []))
        all_themes.update(s.get("themes") or [])

    # Calculate average transition score
    transition_scores = []
    for i in range(len(medley) - 1):
        score = score_transition(medley[i], medley[i + 1], embeddings_data)
        transition_scores.append(score)

    avg_score = sum(transition_scores) / len(transition_scores) if transition_scores else 0

    # Calculate thematic coherence
    thematic_coherence = 0
    if embeddings_data and embeddings_data.get("embeddings") is not None:
        emb_scores = []
        for i in range(len(medley) - 1):
            emb_scores.append(
                emb_lib.embedding_similarity_score(medley[i], medley[i + 1], embeddings_data)
            )
        if emb_scores:
            thematic_coherence = sum(emb_scores) / len(emb_scores)

    return {
        "song_count": len(medley),
        "unique_artists": len(artists),
        "keys": keys,
        "total_unique_chords": len(all_chords),
        "themes_covered": list(all_themes),
        "avg_transition_score": avg_score,
        "thematic_coherence": thematic_coherence,
        "transition_scores": transition_scores,
    }


def generate_medley_tabs(
    medley: list[dict],
    embeddings_data: dict = None,
) -> str:
    """
    Generate a combined tab sheet for the entire medley.

    Reads each tab file and concatenates them with transition suggestions,
    producing a single playable document.
    """
    from pathlib import Path

    lines = []
    stats = analyze_medley(medley, embeddings_data)

    # Header
    lines.append("=" * 70)
    lines.append(f"MEDLEY: {len(medley)} songs")
    lines.append(f"Keys: {' -> '.join(stats['keys'])}")
    lines.append(f"Transition score: {stats['avg_transition_score']:.0%}" +
                 (f" | Thematic coherence: {stats['thematic_coherence']:.0%}" if stats['thematic_coherence'] else ""))
    lines.append("=" * 70)
    lines.append("")

    for i, song in enumerate(medley):
        artist = song.get("artist", "Unknown")
        title = song.get("song", "Unknown")
        key = song.get("key", "?")
        capo = song.get("capo")
        themes = song.get("themes") or []
        file_path = song.get("file_path")

        # Song header
        lines.append("-" * 70)
        lines.append(f"[{i + 1}/{len(medley)}] {title.upper()} - {artist}")

        details = [f"Key: {key}"]
        if capo:
            details.append(f"Capo: {capo}")
        if themes:
            details.append(f"Themes: {', '.join(themes[:3])}")
        lines.append(" | ".join(details))
        lines.append("-" * 70)
        lines.append("")

        # Read and include tab content
        if file_path:
            try:
                content = Path(file_path).read_text(encoding="utf-8")
                # Skip the header (everything before ---)
                if "---" in content:
                    content = content.split("---", 1)[1].strip()
                lines.append(content)
            except Exception as e:
                lines.append(f"[Error reading tab: {e}]")
        else:
            lines.append("[Tab file not found]")

        lines.append("")

        # Transition suggestion to next song
        if i < len(medley) - 1:
            next_song = medley[i + 1]
            transition = suggest_transition(song, next_song, embeddings_data)
            lines.append("")
            lines.append(">" * 70)
            lines.append(f">>> TRANSITION TO: {next_song.get('song', 'Unknown')} - {next_song.get('artist', 'Unknown')}")
            lines.append(f">>> {transition}")
            lines.append(">" * 70)
            lines.append("")
            lines.append("")

    # Footer
    lines.append("=" * 70)
    lines.append("END OF MEDLEY")
    lines.append("=" * 70)

    return "\n".join(lines)
