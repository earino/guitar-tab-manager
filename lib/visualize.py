"""
Embedding visualization for exploring song similarity in 2D/3D space.

Uses dimensionality reduction (t-SNE or PCA) to project high-dimensional
embeddings into 2D/3D, then creates interactive Plotly visualizations.
"""

import json
from pathlib import Path
from typing import Optional

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE


def load_mood_mapping() -> dict[str, str]:
    """Load mood category mapping if it exists."""
    mapping_path = Path("mood_categories.json")
    if mapping_path.exists():
        with open(mapping_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def reduce_dimensions(
    embeddings: np.ndarray,
    method: str = "tsne",
    n_components: int = 2,
    perplexity: int = 30,
    random_state: int = 42,
) -> np.ndarray:
    """
    Reduce embedding dimensions using t-SNE or PCA.

    Args:
        embeddings: High-dimensional embedding matrix (n_samples, n_features)
        method: "tsne" or "pca"
        n_components: 2 or 3 for visualization
        perplexity: t-SNE perplexity (lower for small datasets)
        random_state: For reproducibility

    Returns:
        Reduced coordinates (n_samples, n_components)
    """
    n_samples = embeddings.shape[0]

    if method == "pca":
        reducer = PCA(n_components=n_components, random_state=random_state)
        return reducer.fit_transform(embeddings)

    # t-SNE requires perplexity < n_samples
    # For very small datasets, fall back to PCA
    if n_samples < 5:
        reducer = PCA(n_components=n_components, random_state=random_state)
        return reducer.fit_transform(embeddings)

    # t-SNE - adjust perplexity for small datasets
    effective_perplexity = min(perplexity, max(5, n_samples // 4))
    effective_perplexity = min(effective_perplexity, n_samples - 1)  # Safety cap

    reducer = TSNE(
        n_components=n_components,
        perplexity=effective_perplexity,
        random_state=random_state,
        max_iter=1000,
        learning_rate="auto",
        init="pca",
    )
    return reducer.fit_transform(embeddings)


def get_color_values(tabs: list[dict], color_by: str, max_categories: int = 6) -> tuple[list, str]:
    """
    Extract color values from tabs based on attribute.

    Args:
        tabs: List of tab dictionaries
        color_by: Attribute to color by ("mood", "key", "artist", "theme")
        max_categories: Maximum distinct colors (rest become "other")

    Returns:
        (list of color values, legend title)
    """
    if color_by == "mood":
        # Use primary mood, mapped to categories if available
        mood_mapping = load_mood_mapping()
        values = []
        for tab in tabs:
            moods = tab.get("mood") or []
            if moods:
                raw_mood = moods[0]
                # Apply semantic mapping if available
                mapped = mood_mapping.get(raw_mood, raw_mood)
                values.append(mapped)
            else:
                values.append("unknown")

        # If no mapping exists, fall back to limiting categories
        if not mood_mapping:
            return _limit_categories(values, max_categories), "Mood"
        return values, "Mood"

    elif color_by == "key":
        # Keys are naturally limited (~12), but group unknown
        values = [tab.get("key") or "unknown" for tab in tabs]
        return values, "Key"

    elif color_by == "artist":
        # Too many artists - limit to top N
        raw_values = [tab.get("artist") or "Unknown" for tab in tabs]
        return _limit_categories(raw_values, max_categories), "Artist"

    elif color_by == "theme":
        # Use primary theme, limited to top categories
        raw_values = []
        for tab in tabs:
            themes = tab.get("themes") or []
            raw_values.append(themes[0] if themes else "unknown")
        return _limit_categories(raw_values, max_categories), "Theme"

    elif color_by == "type":
        values = [tab.get("type") or "Unknown" for tab in tabs]
        return values, "Tab Type"

    else:
        # Default to mood
        return get_color_values(tabs, "mood", max_categories)


def _limit_categories(values: list[str], max_categories: int) -> list[str]:
    """Limit to top N categories, bucket rest as 'other'."""
    from collections import Counter

    counts = Counter(values)
    top_categories = {cat for cat, _ in counts.most_common(max_categories)}

    return [v if v in top_categories else "other" for v in values]


def create_hover_text(tab: dict) -> str:
    """Create rich hover text for a song."""
    lines = [
        f"<b>{tab.get('song', 'Unknown')}</b>",
        f"by {tab.get('artist', 'Unknown')}",
    ]

    if tab.get("key"):
        lines.append(f"Key: {tab['key']}")

    if tab.get("mood"):
        lines.append(f"Mood: {', '.join(tab['mood'][:2])}")

    if tab.get("themes"):
        lines.append(f"Themes: {', '.join(tab['themes'][:3])}")

    return "<br>".join(lines)


def create_visualization(
    reduced: np.ndarray,
    tabs: list[dict],
    color_by: str = "mood",
    dim: int = 2,
    title: str = None,
) -> go.Figure:
    """
    Create interactive Plotly visualization.

    Args:
        reduced: Reduced coordinates (n_samples, 2 or 3)
        tabs: Tab metadata for each point
        color_by: Attribute to color points by
        dim: 2 or 3 dimensions
        title: Plot title

    Returns:
        Plotly Figure object
    """
    # Get color values
    colors, legend_title = get_color_values(tabs, color_by)

    # Create hover text
    hover_texts = [create_hover_text(tab) for tab in tabs]

    # Create labels for legend (song names)
    labels = [f"{tab.get('artist', '?')} - {tab.get('song', '?')}" for tab in tabs]

    if dim == 3:
        # 3D scatter with color categories and legend
        fig = px.scatter_3d(
            x=reduced[:, 0],
            y=reduced[:, 1],
            z=reduced[:, 2],
            color=colors,
            hover_name=labels,
            custom_data=[hover_texts],
            title=title or f"Song Embeddings (3D) - Colored by {legend_title}",
            labels={"color": legend_title},
        )

        # Update hover and marker style
        fig.update_traces(
            hovertemplate="%{customdata[0]}<extra></extra>",
            marker=dict(size=5, opacity=0.8),
        )

        fig.update_layout(
            scene=dict(
                xaxis_title="Dimension 1",
                yaxis_title="Dimension 2",
                zaxis_title="Dimension 3",
            ),
            width=1000,
            height=800,
        )
    else:
        # 2D scatter with color categories
        fig = px.scatter(
            x=reduced[:, 0],
            y=reduced[:, 1],
            color=colors,
            hover_name=labels,
            custom_data=[hover_texts],
            title=title or f"Song Embeddings - Colored by {legend_title}",
            labels={"color": legend_title},
        )

        # Update hover template
        fig.update_traces(
            hovertemplate="%{customdata[0]}<extra></extra>",
            marker=dict(size=10, opacity=0.7),
        )

        fig.update_layout(
            width=1200,
            height=800,
            xaxis_title="Dimension 1",
            yaxis_title="Dimension 2",
        )

    return fig


def save_html(fig: go.Figure, output_path: Path) -> None:
    """Save figure as standalone HTML file."""
    fig.write_html(
        str(output_path),
        include_plotlyjs=True,
        full_html=True,
    )
