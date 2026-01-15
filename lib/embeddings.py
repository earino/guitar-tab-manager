"""
Embedding generation and similarity for lyrical/thematic coherence.
"""

import json
from pathlib import Path
from typing import Optional

import numpy as np

import config


def load_embeddings(path: Path = None) -> dict:
    """Load embeddings from numpy file."""
    path = path or Path(config.EMBEDDINGS_FILE)
    if not path.exists():
        return {"file_paths": [], "embeddings": None}

    data = np.load(path, allow_pickle=True)
    return {
        "file_paths": list(data["file_paths"]),
        "embeddings": data["embeddings"],
    }


def save_embeddings(file_paths: list[str], embeddings: np.ndarray, path: Path = None):
    """Save embeddings to numpy file."""
    path = path or Path(config.EMBEDDINGS_FILE)
    np.savez_compressed(
        path,
        file_paths=np.array(file_paths),
        embeddings=embeddings,
    )


def get_embedding_text(tab: dict, content: str) -> str:
    """
    Create the text to embed for a tab.

    Combines song metadata, mood, themes, and lyrics excerpt for rich embeddings.
    """
    parts = []

    # Song identity
    artist = tab.get("artist", "Unknown")
    song = tab.get("song", "Unknown")
    parts.append(f"Song: {song} by {artist}")

    # Mood and themes (if enriched)
    if tab.get("mood"):
        parts.append(f"Mood: {', '.join(tab['mood'])}")
    if tab.get("themes"):
        parts.append(f"Themes: {', '.join(tab['themes'])}")
    if tab.get("description"):
        parts.append(f"Description: {tab['description']}")

    # Extract lyrics from content (skip chord lines, tab notation)
    lyrics = extract_lyrics(content)
    if lyrics:
        # Take first ~500 chars of lyrics for embedding
        parts.append(f"Lyrics: {lyrics[:500]}")

    return "\n".join(parts)


def extract_lyrics(content: str) -> str:
    """Extract just the lyrics from tab content, filtering out chords and notation."""
    import re

    lines = content.split("\n")
    lyric_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip section markers like [Verse], [Chorus]
        if re.match(r'^\[.*\]$', line):
            continue

        # Skip tab notation (lines with |, -, numbers pattern)
        if re.match(r'^[eBGDAE]\|', line) or re.match(r'^[0-9\-|hpx\s]+$', line):
            continue

        # Skip chord diagrams
        if re.match(r'^[xX0-9]{6}$', line):
            continue

        # Skip lines that are mostly chord names
        words = line.split()
        chord_pattern = re.compile(r'^[A-G][#b]?(m|maj|min|dim|aug|sus|add|7|9|11|13)*(/[A-G][#b]?)?$')
        chord_count = sum(1 for w in words if chord_pattern.match(w))
        if len(words) > 0 and chord_count / len(words) > 0.7:
            continue

        # This looks like a lyric line
        # Remove inline chords (words that look like chords)
        cleaned = ' '.join(w for w in words if not chord_pattern.match(w))
        if cleaned and len(cleaned) > 3:
            lyric_lines.append(cleaned)

    return ' '.join(lyric_lines)


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors."""
    if vec1 is None or vec2 is None:
        return 0.0

    dot = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot / (norm1 * norm2)


def find_similar_by_embedding(
    target_embedding: np.ndarray,
    all_embeddings: np.ndarray,
    file_paths: list[str],
    top_k: int = 10,
    exclude_path: str = None,
) -> list[tuple[str, float]]:
    """
    Find most similar items by embedding.

    Returns list of (file_path, similarity_score) tuples.
    """
    if all_embeddings is None or len(all_embeddings) == 0:
        return []

    similarities = []

    for i, (path, emb) in enumerate(zip(file_paths, all_embeddings)):
        if exclude_path and path == exclude_path:
            continue

        sim = cosine_similarity(target_embedding, emb)
        similarities.append((path, sim))

    # Sort by similarity descending
    similarities.sort(key=lambda x: x[1], reverse=True)

    return similarities[:top_k]


def get_embedding_for_tab(
    tab: dict,
    embeddings_data: dict,
) -> Optional[np.ndarray]:
    """Get the embedding for a specific tab from the embeddings data."""
    file_path = tab.get("file_path")
    if not file_path:
        return None

    file_paths = embeddings_data.get("file_paths", [])
    embeddings = embeddings_data.get("embeddings")

    if embeddings is None:
        return None

    try:
        idx = file_paths.index(file_path)
        return embeddings[idx]
    except (ValueError, IndexError):
        return None


def embedding_similarity_score(
    tab_a: dict,
    tab_b: dict,
    embeddings_data: dict,
) -> float:
    """
    Calculate embedding similarity between two tabs.

    Returns 0.0 to 1.0 where higher means more similar lyrics/themes.
    """
    emb_a = get_embedding_for_tab(tab_a, embeddings_data)
    emb_b = get_embedding_for_tab(tab_b, embeddings_data)

    if emb_a is None or emb_b is None:
        return 0.5  # Neutral score if embeddings not available

    # Cosine similarity is -1 to 1, normalize to 0 to 1
    sim = cosine_similarity(emb_a, emb_b)
    return (sim + 1) / 2
