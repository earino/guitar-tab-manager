# Ultimate Guitar Tab Backup Tool

A tool to backup your saved tabs from Ultimate Guitar to local text files.

## Setup

### Prerequisites
- Python 3.9+
- A browser (Chromium will be installed automatically)

### Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

## Usage

### Step 1: Export Your Tabs from Ultimate Guitar

1. Go to https://www.ultimate-guitar.com/user/mytabs
2. Log in to your account
3. Save the page as HTML: File → Save Page As → `guiltar_tabs.html`
4. Place the file in this folder

### Step 2: Extract Tab URLs

```bash
python extract_urls.py
```

This creates `tab_urls.json` with all your saved tab URLs.

### Step 3: Run the Backup

**First time (full backup):**
```bash
python backup_tabs.py
```

A browser window will open. You may need to:
- Log in to Ultimate Guitar (if tabs require authentication)
- Dismiss cookie/privacy dialogs
- Press Enter in the terminal when ready

The script will then download all tabs with progress updates.

**Resume an interrupted backup:**
```bash
python backup_tabs.py
```
Just run the same command - it automatically skips completed tabs.

**Sync new tabs (after adding more favorites):**
```bash
# First, re-export guiltar_tabs.html from the website
python backup_tabs.py --sync
```

**Check status:**
```bash
python backup_tabs.py --status
```

**Retry failed downloads:**
```bash
python backup_tabs.py --retry
```

## Output

Tabs are saved to `tabs/{artist}/{song}.txt`:

```
tabs/
├── counting-crows/
│   └── mr-jones.txt
├── black-sabbath/
│   └── changes.txt
└── ...
```

Each file contains:
```
Song: Mr Jones
Artist: Counting Crows
Type: Chords
URL: https://tabs.ultimate-guitar.com/...
Backed up: 2026-01-15

---

[Intro]
Am F Dm G
...
```

## Configuration

Edit `config.py` to adjust:

```python
# Timing (increase if getting rate limited)
MIN_DELAY = 5          # Min seconds between requests
MAX_DELAY = 15         # Max seconds between requests
BATCH_SIZE = 20        # Tabs before taking a break
BATCH_PAUSE = 60       # Break duration in seconds

# Paths
HTML_FILE = "guiltar_tabs.html"
OUTPUT_DIR = "tabs"
```

## Troubleshooting

### "Rate limited" errors
- Increase `MIN_DELAY` and `MAX_DELAY` in config.py
- Wait a few hours before retrying

### Browser closes unexpectedly
- Just run `python backup_tabs.py` again - it resumes from where it stopped

### Some tabs failed to download
- Run `python backup_tabs.py --retry` to retry failed tabs
- Check `logs/` for error details

### Cookie dialog keeps appearing
- The script tries to auto-dismiss it, but you can manually click "Reject All"
  in the browser window during the initial setup phase

## Files

| File | Purpose |
|------|---------|
| `guiltar_tabs.html` | Your exported favorites (you create this) |
| `tab_urls.json` | Extracted URLs (auto-generated) |
| `backup_manifest.json` | Tracks backup progress (auto-generated) |
| `tabs/` | Your backed up tabs |
| `logs/` | Backup logs |

## Adding New Tabs Later

1. Save new tabs on Ultimate Guitar website
2. Re-export the "My Tabs" page to `guiltar_tabs.html`
3. Run `python backup_tabs.py --sync`
4. Only new tabs will be downloaded
