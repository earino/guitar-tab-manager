# Guitar Tab Manager

A complete system for backing up, exploring, and building setlists from your Ultimate Guitar tab collection. Features intelligent similarity matching and AI-powered medley building with thematic coherence.

## Features

### Backup & Sync
- Download all your saved tabs from Ultimate Guitar
- Resume interrupted backups automatically
- SHA-256 verification and integrity checking
- Incremental sync for new tabs

### Exploration & Search
- **Text search**: Find tabs by artist, song, chord, key, type
- **Semantic search**: Search by mood ("sad songs") or theme ("songs about travel")
- **Chord analysis**: See all chords used in any song

### Similarity Matching
- **Comprehensive similarity**: Combines key compatibility, chord overlap, mood, themes, and lyrical content
- **Chord-based**: Find songs with similar chord progressions
- **Lyrical/thematic**: Find songs with similar meaning via embeddings

### Medley Building
Build coherent setlists that flow naturally:
- **Key compatibility** (30%): Smooth musical transitions
- **Chord overlap** (25%): Easy to play in sequence
- **Mood similarity** (15%): Consistent emotional arc
- **Lyrical coherence** (25%): Narrative makes sense
- **Type matching** (5%): Similar tab formats

## Quick Start

### Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

### Backup Your Tabs

1. Go to https://www.ultimate-guitar.com/user/mytabs
2. Save the page as HTML: `guiltar_tabs.html`
3. Run:
```bash
python backup_tabs.py
```

### Explore Your Collection

```bash
# Build the search index
python tabs.py index

# List all artists
python tabs.py artists

# Find tabs by criteria
python tabs.py find --artist "Beatles" --chord "Am,G"
python tabs.py find --key "Am" --type Chords

# View chords for a song
python tabs.py chords "Hotel California"
```

### Find Similar Songs

```bash
# Comprehensive similarity (all signals)
python tabs.py similar "Hallelujah"

# Just chord similarity
python tabs.py similar "Hallelujah" --by chords

# Just lyrical/thematic similarity
python tabs.py similar "Hallelujah" --by embeddings
```

### Build Medleys

```bash
# Build a 6-song medley
python tabs.py medley "Wish You Were Here" --count 6

# Filter by mood
python tabs.py medley "Yesterday" --mood melancholic
```

## LLM-Powered Features (requires LMStudio)

For semantic search and thematic medleys, you need [LMStudio](https://lmstudio.ai/) running locally.

### Setup LMStudio

1. Download and install LMStudio
2. Load a chat model (e.g., `qwen3-30b`)
3. Load an embedding model (e.g., `text-embedding-nomic-embed-text-v1.5`)
4. Enable the local server (Settings > Local Server)

### Enrich Your Tabs

Analyze all tabs for mood, themes, and tempo:

```bash
python tabs.py enrich
```

This adds metadata like:
- **Mood**: melancholic, uplifting, nostalgic, energetic
- **Themes**: love, loss, travel, freedom, rebellion
- **Tempo feel**: slow, medium, fast

### Generate Embeddings

Create vector embeddings for lyrical/thematic similarity:

```bash
python tabs.py embed
```

Embeddings capture the semantic meaning of each song's:
- Artist and title
- Mood and themes (if enriched)
- Actual lyrics

### Search by Meaning

```bash
python tabs.py search "sad songs about heartbreak"
python tabs.py mood melancholic
python tabs.py theme "lost love"
```

## Example Output

### Similarity Search

```
Finding songs similar to: Jeff Buckley - Hallelujah Chords
(Based on lyrical/thematic similarity via embeddings)

  1. Led Zeppelin - Stairway To Heaven - 70% similar
      Themes: spiritual journey, love
  2. Johnny Cash - Hurt - 68% similar
      Themes: self-destruction, regret
  3. Simon & Garfunkel - Bridge Over Troubled Water - 66% similar
      Themes: support, comfort
  4. Eric Clapton - Tears In Heaven - 65% similar
      Themes: loss, grief
```

### Medley Building

```
Building medley starting from: Jeff Buckley - Hallelujah Chords
Using embeddings for thematic coherence (374 songs)

============================================================
MEDLEY (6 songs)
============================================================

1. Jeff Buckley - Hallelujah Chords [Key: Am, Themes: love, faith]
   -> Same key (Am) | Strong lyrical connection
2. Live - Lightning Crashes Chords [Key: Am, Themes: birth and death]
   -> Same key (Am) | Strong lyrical connection
3. Simon & Garfunkel - Sound of Silence [Key: Am, Themes: isolation]
   -> Same key (Am) | Strong lyrical connection
4. The Beatles - Let It Be [Key: Am, Themes: spiritual comfort]
   ...

------------------------------------------------------------
MEDLEY ANALYSIS
------------------------------------------------------------
Unique artists: 6
Avg transition score: 82.4%
Thematic coherence: 78.1%
Themes: love, faith, isolation, comfort, hope
Keys: Am -> Am -> Am -> Am -> C -> C
```

## Command Reference

### Backup Commands

| Command | Description |
|---------|-------------|
| `python backup_tabs.py` | Run/resume backup |
| `python backup_tabs.py --sync` | Sync new tabs |
| `python backup_tabs.py --status` | Show backup status |
| `python backup_tabs.py --retry` | Retry failed tabs |
| `python backup_tabs.py --verify` | Verify file integrity |

### Exploration Commands

| Command | Description |
|---------|-------------|
| `python tabs.py list` | List all tabs |
| `python tabs.py artists` | List all artists |
| `python tabs.py find` | Search with filters |
| `python tabs.py chords "song"` | Show chords for a song |
| `python tabs.py similar "song"` | Find similar songs |
| `python tabs.py index` | Show collection stats |

### LLM Commands

| Command | Description |
|---------|-------------|
| `python tabs.py enrich` | Add mood/themes via LLM |
| `python tabs.py embed` | Generate embeddings |
| `python tabs.py search "query"` | Semantic search |
| `python tabs.py mood "mood"` | Find by mood |
| `python tabs.py theme "theme"` | Find by theme |
| `python tabs.py medley "song"` | Build a medley |

## Configuration

Edit `config.py`:

```python
# Backup timing
MIN_DELAY = 5           # Seconds between requests
MAX_DELAY = 15
BATCH_SIZE = 20         # Tabs before pause
BATCH_PAUSE = 60        # Pause duration

# LMStudio
LMSTUDIO_URL = "http://localhost:1234/v1"
LMSTUDIO_TIMEOUT = 30

# Paths
OUTPUT_DIR = "tabs"
INDEX_FILE = "tab_index.json"
EMBEDDINGS_FILE = "tab_embeddings.npz"
```

## File Structure

```
guitar-agent/
├── backup_tabs.py          # Tab backup tool
├── tabs.py                 # Exploration CLI
├── config.py               # Configuration
├── lib/
│   ├── parser.py           # Tab file parsing
│   ├── index.py            # Search index
│   ├── search.py           # Search functions
│   ├── music.py            # Music theory (keys, chords)
│   ├── medley.py           # Medley building
│   ├── llm.py              # LMStudio client
│   └── embeddings.py       # Embedding similarity
├── tabs/                   # Your backed up tabs
├── tab_index.json          # Search index (auto-generated)
├── tab_embeddings.npz      # Embeddings (auto-generated)
└── logs/                   # Backup logs
```

## How It Works

### Medley Scoring Algorithm

Each song transition is scored 0-100%:

```
Score = 0.30 * key_compatibility
      + 0.25 * chord_overlap
      + 0.15 * mood_similarity
      + 0.25 * embedding_similarity
      + 0.05 * type_match
```

The algorithm greedily selects the highest-scoring next song while avoiding artist repetition.

### Embedding Generation

Each song's embedding combines:
1. Song identity (artist, title)
2. LLM-generated mood and themes
3. Extracted lyrics (filtered from chord notation)

This creates rich semantic vectors that capture what songs are "about".

## Troubleshooting

### Backup Issues

| Problem | Solution |
|---------|----------|
| Rate limited | Increase delays in config.py |
| Browser closes | Just run again - it resumes |
| Failed tabs | Run `--retry` |

### LLM Issues

| Problem | Solution |
|---------|----------|
| "No models loaded" | Load a model in LMStudio |
| Embedding fails | Load an embedding model (not just chat) |
| Slow enrichment | Normal - ~1 sec per tab |

## License

MIT
