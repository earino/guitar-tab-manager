#!/usr/bin/env python3
"""
Ultimate Guitar Tab Backup Tool

Backup your saved tabs from Ultimate Guitar to local text files.

Usage:
    python backup_tabs.py              # Full backup (resume-aware)
    python backup_tabs.py --sync       # Only download new tabs
    python backup_tabs.py --retry      # Retry failed tabs only
    python backup_tabs.py --status     # Show progress stats
"""

import argparse
import asyncio
import json
import logging
import random
import re
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Page, BrowserContext

import config


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
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "last_sync": None,
        "tabs": {},
    }


def save_manifest(manifest: dict):
    """Save the backup manifest."""
    manifest_path = Path(config.MANIFEST_FILE)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


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
    # Replace problematic characters
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", "-", name)
    name = name.lower().strip("-")
    return name[:100]  # Limit length


def save_tab_file(tab_data: dict, tab_info: dict) -> Path:
    """Save tab content to a text file."""
    artist_dir = sanitize_filename(tab_data["artist"] or tab_info["band_name"])
    song_name = sanitize_filename(tab_data["title"] or tab_info["song_name"])

    # Create directory structure
    output_dir = Path(config.OUTPUT_DIR) / artist_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create file
    file_path = output_dir / f"{song_name}.txt"

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
    file_path.write_text(file_content, encoding="utf-8")

    return file_path


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

        # Save to file
        file_path = save_tab_file(tab_data, tab_info)

        # Update manifest
        update_tab_status(
            manifest,
            url,
            status="completed",
            backed_up_at=datetime.now().isoformat(),
            local_path=str(file_path),
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
                    await context.close()
                    user_agent = random.choice(config.USER_AGENTS)
                    context = await browser.new_context(user_agent=user_agent)
                    page = await context.new_page()
                    # Navigate to base URL to initialize the page properly
                    await page.goto("https://www.ultimate-guitar.com", wait_until="domcontentloaded")
                    await asyncio.sleep(2)  # Let the page settle
                    tabs_since_rotation = 0
                    logger.info("Context rotation complete")
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
                    logger.info("Browser recovery complete")

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
    """Show current backup status."""
    completed = 0
    failed = 0
    pending = 0

    for tab in tabs:
        status = manifest["tabs"].get(tab["url"], {}).get("status")
        if status == "completed":
            completed += 1
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
    print("=" * 50)

    if manifest.get("last_sync"):
        print(f"Last sync: {manifest['last_sync']}")

    if failed > 0:
        print(f"\nTo retry failed tabs: python backup_tabs.py --retry")

    if pending > 0:
        print(f"To continue backup:   python backup_tabs.py")


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
        """,
    )
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

    args = parser.parse_args()

    # Load data
    tabs = load_tab_urls()
    manifest = load_manifest()

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
