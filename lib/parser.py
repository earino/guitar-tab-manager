"""
Tab file parsing and chord extraction.
"""

import re
from pathlib import Path


# Chord pattern: matches chords like A, Am, A7, Amaj7, A#dim, Bb, Csus4, D/F#, etc.
CHORD_PATTERN = re.compile(
    r'\b([A-G][#b]?'                    # Root note (A-G with optional sharp/flat)
    r'(?:maj|min|m|M|dim|aug|sus|add)?'  # Quality
    r'(?:[0-9]+)?'                       # Extension (7, 9, 11, 13)
    r'(?:sus[24])?'                      # Suspended
    r'(?:add[0-9]+)?'                    # Added tone
    r'(?:/[A-G][#b]?)?)'                 # Bass note (slash chord)
    r'\b'
)

# Section pattern: [Verse], [Chorus], [Intro], etc.
SECTION_PATTERN = re.compile(r'\[([A-Za-z0-9\s]+)\]')

# Common noise to filter out from chord extraction
NOISE_PATTERNS = [
    r'^[0-9]+$',           # Pure numbers
    r'^[xX]+$',            # Just x's (muted strings)
    r'^\d+h\d+$',          # Hammer-on notation
    r'^\d+p\d+$',          # Pull-off notation
]


def parse_tab_file(path: Path) -> dict:
    """
    Parse a tab file and extract metadata and content.

    Returns a dict with:
        - file_path: str
        - song: str
        - artist: str
        - type: str
        - url: str
        - capo: int | None
        - content: str (everything after ---)
    """
    content = path.read_text(encoding="utf-8")

    result = {
        "file_path": str(path),
        "song": None,
        "artist": None,
        "type": None,
        "url": None,
        "capo": None,
        "content": "",
    }

    # Split header and content
    if "---" in content:
        header, tab_content = content.split("---", 1)
        result["content"] = tab_content.strip()
    else:
        header = content
        result["content"] = content

    # Parse header fields
    for line in header.split("\n"):
        line = line.strip()
        if line.startswith("Song:"):
            result["song"] = line[5:].strip()
        elif line.startswith("Artist:"):
            result["artist"] = line[7:].strip()
        elif line.startswith("Type:"):
            result["type"] = line[5:].strip()
        elif line.startswith("URL:"):
            result["url"] = line[4:].strip()

    # Extract capo from content
    result["capo"] = extract_capo(result["content"])

    return result


def extract_capo(content: str) -> int | None:
    """Extract capo position from tab content."""
    # Look for patterns like "Capo 3", "Capo: 3", "Capo on 3rd fret"
    patterns = [
        r'[Cc]apo[:\s]+(\d+)',
        r'[Cc]apo\s+on\s+(\d+)',
        r'[Cc]apo\s+(\d+)(?:st|nd|rd|th)',
    ]

    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return int(match.group(1))

    return None


def extract_chords(content: str) -> list[str]:
    """
    Extract unique chords from tab content.

    Returns a sorted list of unique chord names found in the content.
    """
    # Find all potential chords
    matches = CHORD_PATTERN.findall(content)

    # Filter out noise
    chords = set()
    for match in matches:
        # Skip if it matches noise patterns
        is_noise = False
        for noise in NOISE_PATTERNS:
            if re.match(noise, match):
                is_noise = True
                break

        if not is_noise and len(match) <= 10:  # Reasonable chord length
            chords.add(match)

    return sorted(chords)


def extract_sections(content: str) -> list[str]:
    """
    Extract section names from tab content.

    Returns a list of unique section names like ["Intro", "Verse", "Chorus"].
    """
    matches = SECTION_PATTERN.findall(content)

    # Normalize and deduplicate
    sections = []
    seen = set()
    for match in matches:
        # Normalize: "Verse 1" -> "Verse", "CHORUS" -> "Chorus"
        normalized = match.strip().title()
        # Remove trailing numbers for dedup
        base = re.sub(r'\s*\d+$', '', normalized)

        if base not in seen:
            seen.add(base)
            sections.append(base)

    return sections


def has_lyrics(content: str) -> bool:
    """
    Determine if the tab content contains lyrics.

    Heuristic: Look for lines with mostly alphabetic words that aren't
    chord-only lines or tab notation.
    """
    lines = content.split("\n")
    lyric_line_count = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip tab notation lines (contain |, -, numbers in sequence)
        if re.match(r'^[eBGDAE]\|', line) or re.match(r'^[0-9\-|hpx\s]+$', line):
            continue

        # Skip section markers
        if SECTION_PATTERN.match(line):
            continue

        # Skip chord-only lines (just chords and spaces)
        words = line.split()
        if all(CHORD_PATTERN.match(w) for w in words if w):
            continue

        # Check if line has substantial text (lyrics)
        alpha_chars = sum(1 for c in line if c.isalpha())
        if alpha_chars > 10:  # Reasonable threshold for lyric line
            lyric_line_count += 1

    return lyric_line_count >= 3  # At least 3 lines of lyrics


def detect_key(chords: list[str]) -> str | None:
    """
    Attempt to detect the key from a list of chords.

    Simple heuristic: Use the first chord or most common chord as the key.
    """
    if not chords:
        return None

    # Common major keys and their typical chord progressions
    # For now, just return the first chord's root as a simple heuristic
    first_chord = chords[0]

    # Extract root note
    match = re.match(r'^([A-G][#b]?)', first_chord)
    if match:
        root = match.group(1)
        # Check if it's minor
        if 'm' in first_chord and 'maj' not in first_chord:
            return root + "m"
        return root

    return None


def normalize_chord(chord: str) -> str:
    """
    Normalize a chord name for comparison.

    E.g., "Amin" -> "Am", "Cmajor" -> "C"
    """
    # Remove bass note for comparison
    chord = chord.split("/")[0]

    # Normalize common variations
    chord = re.sub(r'maj$', '', chord)  # Cmaj -> C
    chord = re.sub(r'min', 'm', chord)  # Amin -> Am
    chord = re.sub(r'minor', 'm', chord)
    chord = re.sub(r'major', '', chord)

    return chord
