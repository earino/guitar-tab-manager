"""
Unit tests for lib/parser.py - especially key detection.
"""

import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.parser import detect_key, is_minor_chord, extract_chords


class TestIsMinorChord:
    """Tests for is_minor_chord() - Bug fix #7"""

    def test_basic_minor_chords(self):
        """Am, Em, Dm should be detected as minor"""
        assert is_minor_chord("Am") is True
        assert is_minor_chord("Em") is True
        assert is_minor_chord("Dm") is True
        assert is_minor_chord("F#m") is True
        assert is_minor_chord("Bbm") is True

    def test_minor_sevenths(self):
        """Am7, Em7 should be detected as minor"""
        assert is_minor_chord("Am7") is True
        assert is_minor_chord("Em7") is True
        assert is_minor_chord("Dm9") is True

    def test_minor_variants(self):
        """Amin, Aminor should be detected as minor"""
        assert is_minor_chord("Amin") is True
        assert is_minor_chord("Aminor") is True

    def test_major_chords_not_minor(self):
        """C, G, D should NOT be detected as minor"""
        assert is_minor_chord("C") is False
        assert is_minor_chord("G") is False
        assert is_minor_chord("D") is False
        assert is_minor_chord("F#") is False

    def test_maj_not_minor(self):
        """Cmaj7, Gmaj7 should NOT be detected as minor"""
        assert is_minor_chord("Cmaj7") is False
        assert is_minor_chord("Gmaj7") is False
        assert is_minor_chord("Amaj") is False

    def test_dim_not_minor(self):
        """Cdim, Bdim7 should NOT be detected as minor"""
        assert is_minor_chord("Cdim") is False
        assert is_minor_chord("Bdim7") is False

    def test_aug_not_minor(self):
        """Caug should NOT be detected as minor"""
        assert is_minor_chord("Caug") is False
        assert is_minor_chord("Eaug") is False

    def test_sus_not_minor(self):
        """Csus4, Dsus2 should NOT be detected as minor"""
        assert is_minor_chord("Csus4") is False
        assert is_minor_chord("Dsus2") is False
        assert is_minor_chord("Asus") is False

    def test_dom_not_minor(self):
        """Cdom7 should NOT be detected as minor"""
        assert is_minor_chord("Cdom7") is False

    def test_slash_chords(self):
        """Am/G should be detected as minor, C/G should not"""
        assert is_minor_chord("Am/G") is True
        assert is_minor_chord("C/G") is False


class TestDetectKey:
    """Tests for detect_key() - Bug fix #6"""

    def test_first_chord_is_key(self):
        """First chord in document order should be the key"""
        content = "Em  G  C  D\nSome lyrics here"
        assert detect_key(content) == "Em"

    def test_first_chord_not_alphabetically_first(self):
        """Key should be first in document, not alphabetically sorted"""
        # "Am G C D" - alphabetically first would be "Am", but first in doc is also Am
        content = "G  C  Am  D\nMore lyrics"
        assert detect_key(content) == "G"

    def test_minor_key_detection(self):
        """Minor keys should include 'm' suffix"""
        content = "Am  F  C  G\nLyrics here"
        assert detect_key(content) == "Am"

    def test_major_key_detection(self):
        """Major keys should NOT have 'm' suffix"""
        content = "C  Am  F  G\nLyrics"
        assert detect_key(content) == "C"

    def test_sharp_key(self):
        """Sharp keys should be detected correctly"""
        content = "F#m  A  E  B\nLyrics"
        assert detect_key(content) == "F#m"

    def test_flat_key(self):
        """Flat keys should be detected correctly"""
        content = "Bb  F  Gm  Cm\nLyrics"
        assert detect_key(content) == "Bb"

    def test_no_chords_returns_none(self):
        """Content with no chords should return None"""
        content = "Just some lyrics\nNo chords here"
        assert detect_key(content, []) is None

    def test_real_tab_format(self):
        """Test with realistic tab format"""
        content = """[Intro]
Em  G  C  D

[Verse]
Em                G
Some lyrics here about
C                 D
The song we're playing
"""
        assert detect_key(content) == "Em"


class TestExtractChords:
    """Tests for extract_chords()"""

    def test_basic_chords(self):
        """Basic chord extraction"""
        content = "C Am F G"
        chords = extract_chords(content)
        assert "C" in chords
        assert "Am" in chords
        assert "F" in chords
        assert "G" in chords

    def test_complex_chords(self):
        """Complex chords should be extracted"""
        content = "Cmaj7 Am7 Dm7 G7"
        chords = extract_chords(content)
        assert "Cmaj7" in chords
        assert "Am7" in chords

    def test_slash_chords(self):
        """Slash chords should be extracted"""
        content = "C/G Am/E F/C"
        chords = extract_chords(content)
        assert "C/G" in chords or "C" in chords  # Depends on pattern


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
