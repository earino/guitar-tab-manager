"""
Unit tests for lib/visualize.py - especially t-SNE perplexity handling.
"""

import pytest
import numpy as np
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.visualize import reduce_dimensions


class TestReduceDimensions:
    """Tests for reduce_dimensions() - Bug fix #8"""

    def test_normal_dataset_tsne(self):
        """Normal sized dataset should work with t-SNE"""
        embeddings = np.random.rand(100, 50)
        result = reduce_dimensions(embeddings, method="tsne", n_components=2)
        assert result.shape == (100, 2)

    def test_small_dataset_fallback_to_pca(self):
        """Very small dataset (<5) should fall back to PCA"""
        embeddings = np.random.rand(3, 50)
        # Should not crash - falls back to PCA
        result = reduce_dimensions(embeddings, method="tsne", n_components=2)
        assert result.shape == (3, 2)

    def test_exactly_5_samples(self):
        """5 samples should work (edge case)"""
        embeddings = np.random.rand(5, 50)
        result = reduce_dimensions(embeddings, method="tsne", n_components=2)
        assert result.shape == (5, 2)

    def test_pca_works_for_reasonable_sizes(self):
        """PCA should work for datasets >= 2 samples"""
        # PCA n_components must be <= min(n_samples, n_features)
        for n_samples in [2, 3, 5, 10, 100]:
            embeddings = np.random.rand(n_samples, 50)
            result = reduce_dimensions(embeddings, method="pca", n_components=2)
            assert result.shape == (n_samples, 2)

    def test_3d_output(self):
        """3D output should work"""
        embeddings = np.random.rand(50, 100)
        result = reduce_dimensions(embeddings, method="tsne", n_components=3)
        assert result.shape == (50, 3)

    def test_deterministic_with_random_state(self):
        """Same random state should give same results"""
        embeddings = np.random.rand(20, 50)
        result1 = reduce_dimensions(embeddings, method="pca", random_state=42)
        result2 = reduce_dimensions(embeddings, method="pca", random_state=42)
        np.testing.assert_array_equal(result1, result2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
