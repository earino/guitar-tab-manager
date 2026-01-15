"""
Music theory helpers for key compatibility and chord analysis.
"""

# Circle of fifths for major keys
CIRCLE_OF_FIFTHS = ["C", "G", "D", "A", "E", "B", "F#", "Db", "Ab", "Eb", "Bb", "F"]

# Relative minors
RELATIVE_MINOR = {
    "C": "Am", "G": "Em", "D": "Bm", "A": "F#m", "E": "C#m", "B": "G#m",
    "F#": "D#m", "Db": "Bbm", "Ab": "Fm", "Eb": "Cm", "Bb": "Gm", "F": "Dm",
    # Enharmonic equivalents
    "Gb": "Ebm", "C#": "A#m",
}

# Reverse mapping: minor to relative major
RELATIVE_MAJOR = {v: k for k, v in RELATIVE_MINOR.items()}

# All notes for transposition
NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def normalize_key(key: str) -> str:
    """Normalize key name (handle flats, sharps, minor notation)."""
    if not key:
        return None

    key = key.strip()

    # Handle common variations
    key = key.replace("min", "m").replace("minor", "m")
    key = key.replace("maj", "").replace("major", "")

    # Normalize case: root uppercase, m lowercase
    if len(key) >= 1:
        root = key[0].upper()
        rest = key[1:].lower() if len(key) > 1 else ""
        key = root + rest

    return key


def is_minor(key: str) -> bool:
    """Check if a key is minor."""
    if not key:
        return False
    return "m" in key.lower() and "maj" not in key.lower()


def get_root(key: str) -> str:
    """Extract root note from key (e.g., 'Am' -> 'A', 'F#m' -> 'F#')."""
    if not key:
        return None

    key = normalize_key(key)
    if not key:
        return None

    # Extract root (1-2 characters before 'm' or end)
    if key.endswith("m"):
        root = key[:-1]
    else:
        root = key

    # Handle sharps/flats
    if len(root) > 1 and root[1] in "#b":
        return root[:2]
    return root[0] if root else None


def key_to_index(key: str) -> int:
    """Convert key to semitone index (0-11)."""
    root = get_root(key)
    if not root:
        return -1

    # Try sharp notation first
    if root in NOTES:
        return NOTES.index(root)
    # Try flat notation
    if root in NOTES_FLAT:
        return NOTES_FLAT.index(root)

    return -1


def key_distance(key1: str, key2: str) -> int:
    """
    Calculate the distance between two keys in semitones.

    Returns 0-6 (wraps around at 6 for the circle).
    """
    idx1 = key_to_index(key1)
    idx2 = key_to_index(key2)

    if idx1 < 0 or idx2 < 0:
        return 12  # Maximum distance for unknown keys

    diff = abs(idx1 - idx2)
    return min(diff, 12 - diff)


def are_keys_compatible(key1: str, key2: str) -> bool:
    """
    Check if two keys are musically compatible.

    Compatible means:
    - Same key
    - Relative major/minor
    - Adjacent on circle of fifths (up/down a 5th or 4th)
    """
    if not key1 or not key2:
        return False

    key1 = normalize_key(key1)
    key2 = normalize_key(key2)

    # Same key
    if key1 == key2:
        return True

    root1 = get_root(key1)
    root2 = get_root(key2)

    # Relative major/minor
    if is_minor(key1):
        if RELATIVE_MAJOR.get(key1) == key2:
            return True
    else:
        if RELATIVE_MINOR.get(key1) == key2:
            return True

    if is_minor(key2):
        if RELATIVE_MAJOR.get(key2) == key1:
            return True
    else:
        if RELATIVE_MINOR.get(key2) == key1:
            return True

    # Within 2 semitones (allows for some flexibility)
    distance = key_distance(key1, key2)
    return distance <= 2


def transpose_key(key: str, semitones: int) -> str:
    """Transpose a key by a number of semitones."""
    if not key:
        return None

    root = get_root(key)
    minor = is_minor(key)

    idx = key_to_index(key)
    if idx < 0:
        return key

    new_idx = (idx + semitones) % 12
    new_root = NOTES[new_idx]

    return new_root + ("m" if minor else "")


def effective_key(key: str, capo: int) -> str:
    """
    Calculate the effective (sounding) key given a capo position.

    E.g., if playing in Am with capo 2, effective key is Bm.
    """
    if not key or not capo:
        return key

    return transpose_key(key, capo)


def chord_overlap_score(chords1: list[str], chords2: list[str]) -> float:
    """
    Calculate chord overlap between two songs (Jaccard similarity).

    Returns 0.0 to 1.0.
    """
    if not chords1 or not chords2:
        return 0.0

    set1 = set(c.lower() for c in chords1)
    set2 = set(c.lower() for c in chords2)

    intersection = len(set1 & set2)
    union = len(set1 | set2)

    return intersection / union if union > 0 else 0.0


def key_compatibility_score(key1: str, key2: str) -> float:
    """
    Score key compatibility from 0.0 to 1.0.

    1.0 = same key or relative major/minor
    0.8 = adjacent on circle of fifths
    0.5 = 2-3 semitones apart
    0.0 = far apart
    """
    if not key1 or not key2:
        return 0.5  # Unknown, assume neutral

    key1 = normalize_key(key1)
    key2 = normalize_key(key2)

    if key1 == key2:
        return 1.0

    # Check relative major/minor
    if is_minor(key1) and RELATIVE_MAJOR.get(key1) == key2:
        return 1.0
    if not is_minor(key1) and RELATIVE_MINOR.get(key1) == key2:
        return 1.0
    if is_minor(key2) and RELATIVE_MAJOR.get(key2) == key1:
        return 1.0
    if not is_minor(key2) and RELATIVE_MINOR.get(key2) == key1:
        return 1.0

    distance = key_distance(key1, key2)

    if distance <= 1:
        return 0.8
    elif distance <= 2:
        return 0.6
    elif distance <= 3:
        return 0.4
    elif distance <= 4:
        return 0.2
    else:
        return 0.0


def get_common_chords(key: str) -> list[str]:
    """Get common chords for a key (I, IV, V, vi for major; i, iv, v, VI for minor)."""
    root = get_root(key)
    if not root:
        return []

    idx = key_to_index(key)
    if idx < 0:
        return []

    if is_minor(key):
        # Minor key: i, III, iv, v, VI, VII
        return [
            NOTES[idx] + "m",           # i
            NOTES[(idx + 3) % 12],      # III
            NOTES[(idx + 5) % 12] + "m", # iv
            NOTES[(idx + 7) % 12] + "m", # v
            NOTES[(idx + 8) % 12],      # VI
            NOTES[(idx + 10) % 12],     # VII
        ]
    else:
        # Major key: I, ii, iii, IV, V, vi
        return [
            NOTES[idx],                 # I
            NOTES[(idx + 2) % 12] + "m", # ii
            NOTES[(idx + 4) % 12] + "m", # iii
            NOTES[(idx + 5) % 12],      # IV
            NOTES[(idx + 7) % 12],      # V
            NOTES[(idx + 9) % 12] + "m", # vi
        ]
