"""
Configuration settings for Ultimate Guitar Tab Backup Tool.
Adjust these values if you experience rate limiting or want to change paths.
"""

# =============================================================================
# MANIFEST SCHEMA VERSION
# =============================================================================
MANIFEST_VERSION = 2  # Incremented when manifest schema changes

# =============================================================================
# TIMING SETTINGS (Anti-blocking)
# =============================================================================

# Random delay between tab downloads (seconds)
MIN_DELAY = 5
MAX_DELAY = 15

# Batch settings - take a longer pause after processing BATCH_SIZE tabs
BATCH_SIZE = 20
BATCH_PAUSE = 60  # seconds

# Rate limit handling
RATE_LIMIT_WAIT = 300  # 5 minutes wait on HTTP 429
MAX_RETRIES = 3  # Max retries per tab before giving up

# Exponential backoff for connection errors (seconds)
BACKOFF_BASE = 30  # 30s, 60s, 120s...

# =============================================================================
# FILE PATHS
# =============================================================================

# Input: Your exported "My Tabs" HTML file from Ultimate Guitar
HTML_FILE = "guiltar_tabs.html"

# Output: Directory where tab files will be saved
OUTPUT_DIR = "tabs"

# State tracking
MANIFEST_FILE = "backup_manifest.json"
URLS_FILE = "tab_urls.json"

# Logs
LOG_DIR = "logs"

# =============================================================================
# BROWSER SETTINGS
# =============================================================================

# Run browser in headed mode (visible) - set to False for headless
HEADED = True

# Browser context rotation - create fresh context after this many tabs
CONTEXT_ROTATION_SIZE = 50

# User agents to rotate through
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
]
