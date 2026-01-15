"""
Medley building logic for creating song sequences.
"""

from . import music


def score_transition(song_a: dict, song_b: dict) -> float:
    """
    Score how well song_b follows song_a in a medley.

    Returns a score from 0.0 to 1.0 where higher is better.

    Factors:
    - Key compatibility (40%)
    - Chord overlap (30%)
    - Mood similarity (20%) - if available
    - Type match (10%)
    """
    score = 0.0

    # Key compatibility (40%)
    key_a = song_a.get("key")
    key_b = song_b.get("key")
    capo_a = song_a.get("capo") or 0
    capo_b = song_b.get("capo") or 0

    # Use effective key (accounting for capo)
    eff_key_a = music.effective_key(key_a, capo_a) if key_a else None
    eff_key_b = music.effective_key(key_b, capo_b) if key_b else None

    key_score = music.key_compatibility_score(eff_key_a, eff_key_b)
    score += 0.4 * key_score

    # Chord overlap (30%)
    chords_a = song_a.get("chords", [])
    chords_b = song_b.get("chords", [])
    chord_score = music.chord_overlap_score(chords_a, chords_b)
    score += 0.3 * chord_score

    # Mood similarity (20%) - if both have mood data
    moods_a = set(song_a.get("mood") or [])
    moods_b = set(song_b.get("mood") or [])

    if moods_a and moods_b:
        mood_overlap = len(moods_a & moods_b) / len(moods_a | moods_b)
        score += 0.2 * mood_overlap
    else:
        # No mood data, give neutral score
        score += 0.1

    # Type match (10%) - prefer same type (Chords, Tab, etc.)
    type_a = song_a.get("type", "")
    type_b = song_b.get("type", "")
    if type_a and type_b and type_a == type_b:
        score += 0.1
    else:
        score += 0.05

    return score


def find_best_next(
    current: dict,
    candidates: list[dict],
    exclude_artists: set[str] = None,
) -> list[tuple[dict, float]]:
    """
    Find the best next songs to follow the current song.

    Args:
        current: The current song
        candidates: List of candidate songs
        exclude_artists: Artists to exclude (for variety)

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

        score = score_transition(current, candidate)
        scored.append((candidate, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def build_medley(
    start_song: dict,
    all_songs: list[dict],
    count: int = 5,
    diverse: bool = True,
    mood_filter: str = None,
) -> list[dict]:
    """
    Build a medley starting from a seed song.

    Args:
        start_song: The song to start with
        all_songs: All available songs
        count: Number of songs in the medley
        diverse: If True, avoid repeating artists
        mood_filter: Only include songs with this mood

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
        )

        if not scored:
            # If no matches with artist exclusion, try without
            if diverse:
                scored = find_best_next(current, available)

        if not scored:
            break

        # Pick the best
        best_song, _ = scored[0]
        medley.append(best_song)
        used_paths.add(best_song.get("file_path"))
        if diverse:
            used_artists.add(best_song.get("artist"))

    return medley


def suggest_transition(song_a: dict, song_b: dict) -> str:
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
            suggestions.append(f"Same key ({key_a}) - smooth transition")
        elif music.are_keys_compatible(key_a, key_b):
            suggestions.append(f"Compatible keys: {key_a} -> {key_b}")
        else:
            suggestions.append(f"Key change: {key_a} -> {key_b} (may need bridge)")

    # Capo change
    if capo_a != capo_b:
        if capo_a and capo_b:
            suggestions.append(f"Move capo from fret {capo_a} to {capo_b}")
        elif capo_b:
            suggestions.append(f"Add capo at fret {capo_b}")
        elif capo_a:
            suggestions.append(f"Remove capo (was at fret {capo_a})")

    # Common chords
    chords_a = set(song_a.get("chords", []))
    chords_b = set(song_b.get("chords", []))
    common = chords_a & chords_b

    if common:
        common_list = sorted(common)[:4]
        suggestions.append(f"Common chords: {', '.join(common_list)}")

    return " | ".join(suggestions) if suggestions else "No specific transition notes"


def format_medley(medley: list[dict], show_transitions: bool = True) -> str:
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

        line += f" [{', '.join(details)}]"
        lines.append(line)

        # Add transition suggestion
        if show_transitions and i < len(medley):
            next_song = medley[i]
            transition = suggest_transition(song, next_song)
            lines.append(f"   -> {transition}")

    return "\n".join(lines)


def analyze_medley(medley: list[dict]) -> dict:
    """Analyze a medley and return statistics."""
    if not medley:
        return {}

    keys = [s.get("key") for s in medley if s.get("key")]
    artists = set(s.get("artist") for s in medley)
    all_chords = set()
    for s in medley:
        all_chords.update(s.get("chords", []))

    # Calculate average transition score
    transition_scores = []
    for i in range(len(medley) - 1):
        score = score_transition(medley[i], medley[i + 1])
        transition_scores.append(score)

    avg_score = sum(transition_scores) / len(transition_scores) if transition_scores else 0

    return {
        "song_count": len(medley),
        "unique_artists": len(artists),
        "keys": keys,
        "total_unique_chords": len(all_chords),
        "avg_transition_score": avg_score,
        "transition_scores": transition_scores,
    }
