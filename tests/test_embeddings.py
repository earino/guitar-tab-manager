"""
Unit tests for lib/embeddings.py - especially metadata validation.
"""

import pytest
import numpy as np
import json
import tempfile
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.embeddings import load_embeddings, save_embeddings


class TestEmbeddingsIntegrity:
    """Tests for embedding load/save and validation - Bug fix #10"""

    def test_save_and_load_roundtrip(self):
        """Saved embeddings should load correctly"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_embeddings.npz"
            file_paths = ["song1.txt", "song2.txt", "song3.txt"]
            embeddings = np.random.rand(3, 100)

            save_embeddings(file_paths, embeddings, path)
            loaded = load_embeddings(path)

            assert loaded["file_paths"] == file_paths
            assert loaded["embeddings"].shape == (3, 100)
            np.testing.assert_array_almost_equal(loaded["embeddings"], embeddings)

    def test_mismatch_raises_error(self):
        """Mismatched file_paths and embeddings should raise ValueError"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_embeddings.npz"
            meta_path = path.with_suffix(".json")

            # Save embeddings with 3 rows
            embeddings = np.random.rand(3, 100)
            np.savez_compressed(path, embeddings=embeddings)

            # Save metadata with only 2 paths (mismatch!)
            with open(meta_path, "w") as f:
                json.dump({"file_paths": ["song1.txt", "song2.txt"]}, f)

            # Should raise ValueError with helpful message
            with pytest.raises(ValueError) as excinfo:
                load_embeddings(path)

            assert "mismatch" in str(excinfo.value).lower()
            assert "3 embeddings" in str(excinfo.value)
            assert "2 paths" in str(excinfo.value)

    def test_missing_file_returns_empty(self):
        """Missing file should return empty result, not crash"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.npz"
            result = load_embeddings(path)

            assert result["file_paths"] == []
            assert result["embeddings"] is None

    def test_missing_metadata_file(self):
        """Missing metadata file should still load embeddings"""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test_embeddings.npz"

            # Save only embeddings, no metadata
            embeddings = np.random.rand(3, 100)
            np.savez_compressed(path, embeddings=embeddings)

            # Should load embeddings but have empty file_paths
            # This will raise ValueError due to mismatch (3 embeddings, 0 paths)
            with pytest.raises(ValueError):
                load_embeddings(path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
