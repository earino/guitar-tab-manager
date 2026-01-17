#!/usr/bin/env python3
"""
Ultimate Guitar Tab Backup Tool

Backup your saved tabs from Ultimate Guitar to local text files.

Usage:
    python backup_tabs.py              # Full backup (resume-aware)
    python backup_tabs.py --sync       # Only download new tabs
    python backup_tabs.py --retry      # Retry failed tabs only
    python backup_tabs.py --status     # Show progress stats

Verification:
    python backup_tabs.py --verify              # Check all file integrity
    python backup_tabs.py --verify --fix        # Check and mark broken for re-download
    python backup_tabs.py --verify --verbose    # Show details for each file

Recovery:
    python backup_tabs.py --rebuild-manifest    # Rebuild manifest from files on disk
    python backup_tabs.py --find-orphans        # Find untracked files
"""

import argparse
import asyncio
import hashlib
import json
import logging
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page, BrowserContext

import config

# Manifest version for schema compatibility
MANIFEST_VERSION = 2


# =============================================================================
# LOGGING SETUP
# =============================================================================

def setup_logging():
    """Configure logging to both file and console."""
    log_dir = Path(config.LOG_DIR)
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"backup_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger(__name__)


logger = setup_logging()


# =============================================================================
# MANIFEST MANAGEMENT
# =============================================================================

def load_manifest() -> dict:
    """Load the backup manifest, creating if it doesn't exist."""
    manifest_path = Path(config.MANIFEST_FILE)
    if manifest_path.exists():
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Manifest corrupted ({e}), starting fresh. "
                          f"Old manifest backed up to {manifest_path}.corrupt")
            manifest_path.rename(manifest_path.with_suffix(".json.corrupt"))
    return {
        "last_sync": None,
        "tabs": {},
    }


def save_manifest(manifest: dict):
    """Save the backup manifest atomically."""
    manifest_path = Path(config.MANIFEST_FILE)
    temp_path = manifest_path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temp_path.replace(manifest_path)  # Atomic on POSIX, safer on Windows


def update_tab_status(manifest: dict, url: str, status: str, **kwargs):
    """Update the status of a tab in the manifest."""
    if url not in manifest["tabs"]:
        manifest["tabs"][url] = {}

    manifest["tabs"][url]["status"] = status
    manifest["tabs"][url]["updated_at"] = datetime.now().isoformat()

    for key, value in kwargs.items():
        manifest["tabs"][url][key] = value

    save_manifest(manifest)


# =============================================================================
# FILE INTEGRITY & VERIFICATION
# =============================================================================

def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return f"sha256:{sha256.hexdigest()}"


def validate_file_structure(file_path: Path) -> tuple[bool, str]:
    """
    Validate that a tab file has the expected structure.
    Returns (is_valid, error_message).
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Cannot read file: {e}"

    # Check for header fields
    required_fields = ["Song:", "Artist:", "URL:"]
    for field in required_fields:
        if field not in content:
            return False, f"Missing required field: {field}"

    # Check for separator
    if "---" not in content:
        return False, "Missing separator (---)"

    # Check for content after separator
    parts = content.split("---", 1)
    if len(parts) < 2 or len(parts[1].strip()) < 10:
        return False, "Missing or empty tab content after separator"

    return True, ""


def extract_url_from_file(file_path: Path) -> str | None:
    """Extract the URL from a tab file's header."""
    try:
        content = file_path.read_text(encoding="utf-8")
        for line in content.split("\n"):
            if line.startswith("URL:"):
                return line[4:].strip()
    except Exception:
        pass
    return None


def verify_single_file(url: str, tab_info: dict, tabs_dir: Path) -> dict:
    """
    Verify a single backed-up tab file.
    Returns a dict with verification results.
    """
    result = {
        "url": url,
        "status": "ok",
        "issues": [],
    }

    local_path = tab_info.get("local_path")
    if not local_path:
        result["status"] = "missing"
        result["issues"].append("No local_path in manifest")
        return result

    file_path = Path(local_path)
    if not file_path.is_absolute():
        file_path = tabs_dir.parent / file_path

    # Check 1: File exists
    if not file_path.exists():
        result["status"] = "missing"
        result["issues"].append(f"File not found: {local_path}")
        return result

    # Check 2: Hash matches (if we have a stored hash)
    stored_hash = tab_info.get("file_hash")
    if stored_hash:
        current_hash = compute_file_hash(file_path)
        if current_hash != stored_hash:
            result["status"] = "corrupted"
            result["issues"].append(f"Hash mismatch: expected {stored_hash[:20]}..., got {current_hash[:20]}...")

    # Check 3: File structure is valid
    is_valid, error = validate_file_structure(file_path)
    if not is_valid:
        result["status"] = "invalid"
        result["issues"].append(f"Invalid structure: {error}")

    # Check 4: URL in file matches manifest URL
    file_url = extract_url_from_file(file_path)
    if file_url and file_url != url:
        result["status"] = "invalid"
        result["issues"].append(f"URL mismatch: file has {file_url}")

    # Check 5: File size matches (if stored)
    stored_size = tab_info.get("file_size")
    if stored_size:
        actual_size = file_path.stat().st_size
        if actual_size != stored_size:
            if result["status"] == "ok":
                result["status"] = "corrupted"
            result["issues"].append(f"Size mismatch: expected {stored_size}, got {actual_size}")

    return result


def verify_all_files(manifest: dict, verbose: bool = False) -> dict:
    """
    Verify all completed tabs in the manifest.
    Returns summary statistics and list of issues.
    """
    tabs_dir = Path(config.OUTPUT_DIR)
    completed_tabs = {
        url: info for url, info in manifest.get("tabs", {}).items()
        if info.get("status") == "completed"
    }

    results = {
        "total": len(completed_tabs),
        "passed": 0,
        "missing": 0,
        "corrupted": 0,
        "invalid": 0,
        "issues": [],
    }

    for i, (url, tab_info) in enumerate(completed_tabs.items(), 1):
        if verbose:
            print(f"\r[{i}/{results['total']}] Verifying...", end="", flush=True)

        result = verify_single_file(url, tab_info, tabs_dir)

        if result["status"] == "ok":
            results["passed"] += 1
        else:
            results[result["status"]] += 1
            results["issues"].append(result)

    if verbose:
        print()  # Newline after progress

    return results


def find_orphan_files(manifest: dict) -> list[Path]:
    """Find files in tabs/ directory that aren't tracked in manifest."""
    tabs_dir = Path(config.OUTPUT_DIR)
    if not tabs_dir.exists():
        return []

    # Get all tracked paths from manifest
    tracked_paths = set()
    for tab_info in manifest.get("tabs", {}).values():
        local_path = tab_info.get("local_path")
        if local_path:
            # Normalize path
            path = Path(local_path)
            if not path.is_absolute():
                path = tabs_dir.parent / path
            tracked_paths.add(path.resolve())

    # Find all .txt files in tabs directory
    all_files = set(p.resolve() for p in tabs_dir.glob("**/*.txt"))

    # Orphans are files not in tracked paths
    orphans = sorted(all_files - tracked_paths)
    return orphans


def rebuild_manifest_from_files() -> dict:
    """
    Rebuild manifest from existing tab files on disk.
    Useful for recovery if manifest is lost/corrupted.
    """
    tabs_dir = Path(config.OUTPUT_DIR)
    if not tabs_dir.exists():
        logger.error(f"Tabs directory not found: {tabs_dir}")
        return {"version": MANIFEST_VERSION, "tabs": {}}

    manifest = {
        "version": MANIFEST_VERSION,
        "last_sync": None,
        "rebuilt_at": datetime.now().isoformat(),
        "tabs": {},
    }

    files = list(tabs_dir.glob("**/*.txt"))
    logger.info(f"Found {len(files)} tab files to process...")

    for i, file_path in enumerate(files, 1):
        if i % 50 == 0:
            logger.info(f"Processing file {i}/{len(files)}...")

        # Extract URL from file header
        url = extract_url_from_file(file_path)
        if not url:
            logger.warning(f"Could not extract URL from: {file_path}")
            continue

        # Validate structure
        is_valid, error = validate_file_structure(file_path)
        if not is_valid:
            logger.warning(f"Invalid file structure in {file_path}: {error}")

        # Extract metadata from header
        try:
            content = file_path.read_text(encoding="utf-8")
            metadata = {}
            for line in content.split("\n"):
                if line.startswith("Song:"):
                    metadata["song"] = line[5:].strip()
                elif line.startswith("Artist:"):
                    metadata["artist"] = line[7:].strip()
                elif line.startswith("Type:"):
                    metadata["type"] = line[5:].strip()
                elif line.startswith("Backed up:"):
                    metadata["backed_up_at"] = line[10:].strip()
                elif line.startswith("---"):
                    break
        except Exception as e:
            logger.warning(f"Error reading metadata from {file_path}: {e}")
            metadata = {}

        # Compute hash
        file_hash = compute_file_hash(file_path)
        file_size = file_path.stat().st_size

        # Add to manifest
        manifest["tabs"][url] = {
            "status": "completed",
            "local_path": str(file_path),
            "file_hash": file_hash,
            "file_size": file_size,
            "song": metadata.get("song", "Unknown"),
            "artist": metadata.get("artist", "Unknown"),
            "rebuilt": True,
        }

    logger.info(f"Rebuilt manifest with {len(manifest['tabs'])} tabs")
    return manifest


# =============================================================================
# URL LOADING
# =============================================================================

def load_tab_urls() -> list[dict]:
    """Load tab URLs from the extracted JSON file."""
    urls_path = Path(config.URLS_FILE)
    if not urls_path.exists():
        logger.error(f"Tab URLs file not found: {urls_path}")
        logger.error("Run 'python extract_urls.py' first to extract URLs from your HTML export.")
        sys.exit(1)

    return json.loads(urls_path.read_text(encoding="utf-8"))


# =============================================================================
# TAB EXTRACTION
# =============================================================================

async def handle_popups(page: Page):
    """Try to dismiss common popups and dialogs."""
    try:
        # Cookie consent - try multiple common button texts
        for text in ["I Do Not Accept", "Reject All", "Decline", "No Thanks"]:
            try:
                button = page.get_by_role("button", name=text)
                if await button.is_visible(timeout=1000):
                    await button.click()
                    await asyncio.sleep(0.5)
                    logger.debug(f"Dismissed popup with button: {text}")
                    return
            except Exception:
                pass

        # Try clicking any dismiss buttons
        dismiss_buttons = page.locator("button:has-text('Dismiss')")
        if await dismiss_buttons.count() > 0:
            await dismiss_buttons.first.click()
            await asyncio.sleep(0.5)

    except Exception as e:
        logger.debug(f"No popups to dismiss: {e}")


async def extract_tab_content(page: Page) -> dict | None:
    """Extract tab content and metadata from the page."""
    try:
        # Wait for the content to load
        await page.wait_for_selector("code", timeout=10000)

        # Extract content
        content = await page.evaluate("document.querySelector('code')?.textContent")
        if not content:
            return None

        # Extract metadata
        title = await page.evaluate("document.querySelector('h1')?.textContent")
        artist = await page.evaluate(
            "document.querySelector('h1')?.parentElement?.querySelector('a')?.textContent"
        )

        # Try to get tuning, key, capo
        tuning = await page.evaluate("""
            (() => {
                const el = document.querySelector('[class*="Tuning"]');
                return el ? el.textContent : null;
            })()
        """)

        return {
            "title": (title or "").strip(),
            "artist": (artist or "").strip(),
            "content": content,
            "tuning": tuning,
            "url": page.url,
        }

    except Exception as e:
        logger.error(f"Failed to extract content: {e}")
        return None


def sanitize_filename(name: str) -> str:
    """Convert a string to a safe filename."""
    # Remove null bytes (could truncate on some systems)
    name = name.replace("\x00", "")
    # Remove path traversal sequences
    name = name.replace("..", "")
    # Replace problematic characters
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", "-", name)
    name = name.lower().strip("-")
    # Ensure non-empty result
    name = name[:100] if name else "unnamed"
    return name


def validate_path_within_dir(file_path: Path, base_dir: Path) -> bool:
    """Ensure file_path is within base_dir (prevent path traversal)."""
    try:
        resolved = file_path.resolve()
        base_resolved = base_dir.resolve()
        return str(resolved).startswith(str(base_resolved) + "/") or resolved == base_resolved
    except (OSError, ValueError):
        return False


def is_safe_tab_url(url: str) -> bool:
    """Validate URL is from Ultimate Guitar (prevent SSRF)."""
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme == "https"
            and parsed.netloc == "tabs.ultimate-guitar.com"
            and parsed.path.startswith("/tab/")
        )
    except Exception:
        return False


def save_tab_file(tab_data: dict, tab_info: dict) -> tuple[Path, str, int]:
    """
    Save tab content to a text file using atomic writes.

    Returns (file_path, file_hash, file_size).
    """
    artist_dir = sanitize_filename(tab_data["artist"] or tab_info["band_name"])
    song_name = sanitize_filename(tab_data["title"] or tab_info["song_name"])
    tab_type = sanitize_filename(tab_info.get("type", "tab"))

    # Create directory structure
    base_dir = Path(config.OUTPUT_DIR)
    output_dir = base_dir / artist_dir

    # Target file path (include type to avoid collisions between Chords/Tab/Bass versions)
    file_path = output_dir / f"{song_name}-{tab_type}.txt"

    # Security: validate path stays within OUTPUT_DIR
    if not validate_path_within_dir(file_path, base_dir):
        raise ValueError(f"Path traversal detected: {file_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(".txt.tmp")

    # Build file content with metadata header
    header = f"""Song: {tab_data['title'] or tab_info['song_name']}
Artist: {tab_data['artist'] or tab_info['band_name']}
Type: {tab_info['type']}
URL: {tab_data['url']}
Backed up: {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    if tab_data.get("tuning"):
        header += f"Tuning: {tab_data['tuning']}\n"

    header += "\n---\n\n"

    file_content = header + tab_data["content"]

    # Atomic write: write to temp file first, then rename
    try:
        temp_path.write_text(file_content, encoding="utf-8")
        temp_path.rename(file_path)
    except Exception:
        # Clean up temp file if rename fails
        if temp_path.exists():
            temp_path.unlink()
        raise

    # Compute hash and size for integrity tracking
    file_hash = compute_file_hash(file_path)
    file_size = file_path.stat().st_size

    return file_path, file_hash, file_size


# =============================================================================
# BACKUP LOGIC
# =============================================================================

async def backup_single_tab(
    page: Page,
    tab_info: dict,
    manifest: dict,
) -> str:
    """
    Backup a single tab. Returns status: 'success', 'failed', or 'skipped'.
    """
    url = tab_info["url"]

    # Security: validate URL before navigation (prevent SSRF)
    if not is_safe_tab_url(url):
        logger.error(f"Invalid URL rejected: {url}")
        return "failed"

    # Check if already completed
    if manifest["tabs"].get(url, {}).get("status") == "completed":
        return "skipped"

    try:
        logger.info(f"Backing up: {tab_info['band_name']} - {tab_info['song_name']}")

        # Navigate to the tab
        await page.goto(url, wait_until="networkidle", timeout=30000)

        # Handle any popups
        await handle_popups(page)

        # Extract content
        tab_data = await extract_tab_content(page)

        if not tab_data or not tab_data.get("content"):
            raise Exception("Failed to extract tab content")

        # Save to file (atomic write with hash computation)
        file_path, file_hash, file_size = save_tab_file(tab_data, tab_info)

        # Update manifest with integrity info
        update_tab_status(
            manifest,
            url,
            status="completed",
            backed_up_at=datetime.now().isoformat(),
            local_path=str(file_path),
            file_hash=file_hash,
            file_size=file_size,
            artist=tab_info["band_name"],
            song=tab_info["song_name"],
        )

        logger.info(f"  Saved: {file_path}")
        return "success"

    except Exception as e:
        retry_count = manifest["tabs"].get(url, {}).get("retry_count", 0) + 1
        update_tab_status(
            manifest,
            url,
            status="failed",
            error=str(e),
            retry_count=retry_count,
        )
        logger.error(f"  Failed: {e}")

        # Exponential backoff on failure
        if retry_count <= config.MAX_RETRIES:
            backoff = config.BACKOFF_BASE * (2 ** (retry_count - 1))
            logger.info(f"  Backing off {backoff}s before next request (retry {retry_count}/{config.MAX_RETRIES})")
            await asyncio.sleep(backoff)

        return "failed"


async def random_delay():
    """Wait a random amount of time between requests."""
    delay = random.uniform(config.MIN_DELAY, config.MAX_DELAY)
    # Add jitter
    delay += random.uniform(-2, 2)
    delay = max(1, delay)  # Minimum 1 second
    logger.debug(f"Waiting {delay:.1f} seconds...")
    await asyncio.sleep(delay)


async def run_backup(
    tabs: list[dict],
    manifest: dict,
    mode: str = "backup",
):
    """
    Run the backup process for a list of tabs.

    Modes:
    - 'backup': Process all tabs that aren't completed
    - 'retry': Only process failed tabs
    - 'sync': Only process tabs not in manifest
    """
    # Filter tabs based on mode
    if mode == "retry":
        tabs_to_process = [
            t for t in tabs
            if manifest["tabs"].get(t["url"], {}).get("status") == "failed"
        ]
    elif mode == "sync":
        existing_urls = set(manifest["tabs"].keys())
        tabs_to_process = [t for t in tabs if t["url"] not in existing_urls]
    else:  # backup mode
        tabs_to_process = [
            t for t in tabs
            if manifest["tabs"].get(t["url"], {}).get("status") != "completed"
        ]

    if not tabs_to_process:
        logger.info("No tabs to process!")
        return

    logger.info(f"Processing {len(tabs_to_process)} tabs...")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not config.HEADED)

        # Select a random user agent
        user_agent = random.choice(config.USER_AGENTS)

        context = await browser.new_context(user_agent=user_agent)
        page = await context.new_page()

        # Initial page load - let user handle login/dialogs
        logger.info("\n" + "=" * 60)
        logger.info("Browser opened. Please:")
        logger.info("  1. Log in to Ultimate Guitar if needed")
        logger.info("  2. Dismiss any cookie/privacy dialogs")
        logger.info("  3. Press Enter in this terminal when ready")
        logger.info("=" * 60 + "\n")

        await page.goto("https://www.ultimate-guitar.com", wait_until="networkidle")
        input("Press Enter when ready to start backup...")

        stats = {"success": 0, "failed": 0, "skipped": 0}
        tabs_since_rotation = 0

        for i, tab_info in enumerate(tabs_to_process, 1):
            # Progress indicator
            logger.info(f"\n[{i}/{len(tabs_to_process)}] ", )

            # Backup the tab
            result = await backup_single_tab(page, tab_info, manifest)
            stats[result] += 1
            tabs_since_rotation += 1

            # Rotate browser context periodically
            if tabs_since_rotation >= config.CONTEXT_ROTATION_SIZE:
                logger.info("Rotating browser context...")
                try:
                    # Save auth state before closing
                    storage_state = await context.storage_state()
                    await context.close()
                    user_agent = random.choice(config.USER_AGENTS)
                    context = await browser.new_context(
                        user_agent=user_agent,
                        storage_state=storage_state  # Preserve auth
                    )
                    page = await context.new_page()
                    # Navigate to base URL to initialize the page properly
                    await page.goto("https://www.ultimate-guitar.com", wait_until="domcontentloaded")
                    await asyncio.sleep(2)  # Let the page settle
                    tabs_since_rotation = 0
                    logger.info("Context rotation complete (auth preserved)")
                except Exception as e:
                    logger.error(f"Context rotation failed: {e}, attempting recovery...")
                    try:
                        await browser.close()
                    except Exception:
                        pass
                    browser = await p.chromium.launch(headless=not config.HEADED)
                    context = await browser.new_context(user_agent=random.choice(config.USER_AGENTS))
                    page = await context.new_page()
                    await page.goto("https://www.ultimate-guitar.com", wait_until="domcontentloaded")
                    tabs_since_rotation = 0
                    logger.info("Browser recovery complete (may need re-auth)")

            # Batch pause
            if i % config.BATCH_SIZE == 0 and i < len(tabs_to_process):
                logger.info(f"\nBatch complete. Pausing for {config.BATCH_PAUSE} seconds...")
                await asyncio.sleep(config.BATCH_PAUSE)

            # Random delay between tabs
            if i < len(tabs_to_process):
                await random_delay()

        await context.close()
        await browser.close()

    # Update manifest sync time
    manifest["last_sync"] = datetime.now().isoformat()
    save_manifest(manifest)

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("BACKUP COMPLETE")
    logger.info(f"  Success: {stats['success']}")
    logger.info(f"  Failed:  {stats['failed']}")
    logger.info(f"  Skipped: {stats['skipped']}")
    logger.info("=" * 60)


def show_status(tabs: list[dict], manifest: dict):
    """Show current backup status with integrity information."""
    completed = 0
    failed = 0
    pending = 0
    with_hash = 0

    for tab in tabs:
        tab_info = manifest["tabs"].get(tab["url"], {})
        status = tab_info.get("status")
        if status == "completed":
            completed += 1
            if tab_info.get("file_hash"):
                with_hash += 1
        elif status == "failed":
            failed += 1
        else:
            pending += 1

    total = len(tabs)

    print("\n" + "=" * 50)
    print("BACKUP STATUS")
    print("=" * 50)
    print(f"Total tabs:  {total}")
    print(f"Completed:   {completed} ({100*completed/total:.1f}%)")
    print(f"Failed:      {failed}")
    print(f"Pending:     {pending}")
    print("-" * 50)
    print("INTEGRITY TRACKING")
    print("-" * 50)
    print(f"With hash:   {with_hash}/{completed} completed tabs")
    if manifest.get("last_verify"):
        print(f"Last verify: {manifest['last_verify']}")
    else:
        print("Last verify: Never")
    print("=" * 50)

    if manifest.get("last_sync"):
        print(f"Last sync: {manifest['last_sync']}")

    if failed > 0:
        print(f"\nTo retry failed tabs: python backup_tabs.py --retry")

    if pending > 0:
        print(f"To continue backup:   python backup_tabs.py")

    if completed > 0:
        print(f"To verify integrity:  python backup_tabs.py --verify")


# =============================================================================
# VERIFICATION COMMANDS
# =============================================================================

def run_verify(manifest: dict, fix: bool = False, verbose: bool = False):
    """Run verification on all completed tabs."""
    print("\nVerifying completed tabs...")

    results = verify_all_files(manifest, verbose=verbose)

    print("\n" + "=" * 50)
    print("VERIFICATION COMPLETE")
    print("=" * 50)
    print(f"Total checked:  {results['total']}")
    print(f"Passed:         {results['passed']} ({100*results['passed']/max(results['total'],1):.1f}%)")
    print(f"Missing:        {results['missing']}")
    print(f"Corrupted:      {results['corrupted']}")
    print(f"Invalid:        {results['invalid']}")
    print("=" * 50)

    # Show issues
    if results["issues"]:
        print("\nIssues found:")
        for issue in results["issues"]:
            status = issue["status"].upper()
            url = issue["url"]
            # Get song info from manifest
            tab_info = manifest["tabs"].get(url, {})
            song = tab_info.get("song", "Unknown")
            artist = tab_info.get("artist", "Unknown")
            print(f"  {status}: {artist} - {song}")
            for problem in issue["issues"]:
                print(f"      {problem}")

        if fix:
            print("\nMarking broken files for re-download...")
            for issue in results["issues"]:
                url = issue["url"]
                update_tab_status(
                    manifest,
                    url,
                    status="failed",
                    error=f"Verification failed: {issue['status']}",
                    needs_redownload=True,
                )
            print(f"Marked {len(results['issues'])} tabs for re-download.")
            print("Run 'python backup_tabs.py --retry' to re-download them.")
        else:
            print("\nRun with --fix to mark broken files for re-download.")
    else:
        print("\nAll files passed verification!")

    # Update manifest with verification timestamp
    manifest["last_verify"] = datetime.now().isoformat()
    save_manifest(manifest)


def run_rebuild_manifest():
    """Rebuild manifest from files on disk."""
    print("\nRebuilding manifest from files on disk...")
    print("This will create a new manifest based on existing tab files.\n")

    # Check if manifest already exists
    manifest_path = Path(config.MANIFEST_FILE)
    if manifest_path.exists():
        response = input("Existing manifest found. Overwrite? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return

    manifest = rebuild_manifest_from_files()

    # Save the rebuilt manifest
    save_manifest(manifest)

    print(f"\nManifest rebuilt successfully!")
    print(f"Found {len(manifest['tabs'])} tabs in {config.OUTPUT_DIR}/")


def run_rehash(manifest: dict):
    """Compute and store hashes for all completed files that don't have them."""
    print("\nComputing hashes for existing files...")

    tabs_dir = Path(config.OUTPUT_DIR)
    updated = 0
    skipped = 0
    missing = 0

    completed_tabs = {
        url: info for url, info in manifest.get("tabs", {}).items()
        if info.get("status") == "completed"
    }

    total = len(completed_tabs)
    for i, (url, tab_info) in enumerate(completed_tabs.items(), 1):
        if i % 50 == 0 or i == total:
            print(f"\r[{i}/{total}] Processing...", end="", flush=True)

        # Skip if already has hash
        if tab_info.get("file_hash"):
            skipped += 1
            continue

        local_path = tab_info.get("local_path")
        if not local_path:
            missing += 1
            continue

        file_path = Path(local_path)
        if not file_path.is_absolute():
            file_path = tabs_dir.parent / file_path

        if not file_path.exists():
            missing += 1
            continue

        # Compute hash and size
        file_hash = compute_file_hash(file_path)
        file_size = file_path.stat().st_size

        # Update manifest entry
        tab_info["file_hash"] = file_hash
        tab_info["file_size"] = file_size
        updated += 1

    print()  # Newline after progress

    # Save updated manifest
    save_manifest(manifest)

    print(f"\nRehashing complete!")
    print(f"  Updated:  {updated}")
    print(f"  Skipped:  {skipped} (already had hash)")
    print(f"  Missing:  {missing} (file not found)")


def run_find_orphans(manifest: dict):
    """Find files not tracked in manifest."""
    print("\nSearching for orphan files...")

    orphans = find_orphan_files(manifest)

    if not orphans:
        print("No orphan files found. All files are tracked in manifest.")
        return

    print(f"\nFound {len(orphans)} orphan file(s) not tracked in manifest:\n")
    for orphan in orphans:
        print(f"  {orphan}")

    print("\nThese files exist on disk but are not in the backup manifest.")
    print("They may be:")
    print("  - Manually added files")
    print("  - Files from a previous backup with lost manifest")
    print("  - Remnants from interrupted operations")
    print("\nOptions:")
    print("  - Run --rebuild-manifest to create a fresh manifest including these files")
    print("  - Manually delete them if they're not needed")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Backup your Ultimate Guitar tabs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backup_tabs.py              # Full backup (resume-aware)
  python backup_tabs.py --sync       # Only download new tabs
  python backup_tabs.py --retry      # Retry failed tabs only
  python backup_tabs.py --status     # Show progress stats

Verification:
  python backup_tabs.py --verify              # Check all file integrity
  python backup_tabs.py --verify --fix        # Check and mark broken for re-download
  python backup_tabs.py --verify --verbose    # Show details for each file

Recovery:
  python backup_tabs.py --rebuild-manifest    # Rebuild manifest from files on disk
  python backup_tabs.py --find-orphans        # Find untracked files
        """,
    )

    # Backup modes
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Only download tabs not in manifest (for incremental backups)",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="Only retry previously failed tabs",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current backup status",
    )

    # Verification
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify integrity of all backed up files",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="With --verify: mark broken files for re-download",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output",
    )

    # Recovery
    parser.add_argument(
        "--rebuild-manifest",
        action="store_true",
        help="Rebuild manifest from files on disk (recovery)",
    )
    parser.add_argument(
        "--find-orphans",
        action="store_true",
        help="Find files not tracked in manifest",
    )
    parser.add_argument(
        "--rehash",
        action="store_true",
        help="Compute hashes for existing files (run once after upgrade)",
    )

    args = parser.parse_args()

    # Handle rebuild-manifest first (doesn't need tab URLs)
    if args.rebuild_manifest:
        run_rebuild_manifest()
        return

    # Load manifest (needed for most operations)
    manifest = load_manifest()

    # Handle find-orphans (doesn't need tab URLs)
    if args.find_orphans:
        run_find_orphans(manifest)
        return

    # Handle rehash (doesn't need tab URLs)
    if args.rehash:
        run_rehash(manifest)
        return

    # Handle verify (doesn't need tab URLs)
    if args.verify:
        run_verify(manifest, fix=args.fix, verbose=args.verbose)
        return

    # Load tab URLs (needed for remaining operations)
    tabs = load_tab_urls()

    if args.status:
        show_status(tabs, manifest)
        return

    # Determine mode
    if args.retry:
        mode = "retry"
    elif args.sync:
        mode = "sync"
    else:
        mode = "backup"

    # Run backup
    asyncio.run(run_backup(tabs, manifest, mode))


if __name__ == "__main__":
    main()
