"""Crawler runner script for NGX Index Funds.

Runs spiders for NGX Oil & Gas and Afrinvest Dividend Yield Index,
writing the results atomically to index_funds/oil_gas.json and
index_funds/afribank.json after verifying the crawled data is valid and non-empty.
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
INDEX_FUNDS_DIR = BASE_DIR / "index_funds"
STATUS_FILE = BASE_DIR / "index_funds" / "crawl_status.json"

SPIDERS = [
    {
        "name": "oil_and_gas",
        "output_file": INDEX_FUNDS_DIR / "oil_gas.json",
        "min_items": 3,
    },
    {
        "name": "afribank_div_yield",
        "output_file": INDEX_FUNDS_DIR / "afribank.json",
        "min_items": 5,
    },
]


def update_status(status: str, message: str = "", details: Dict[str, Any] = None):
    """Save crawl status to a JSON file for monitoring."""
    payload = {
        "status": status,
        "message": message,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "details": details or {},
    }
    try:
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not update status file: {e}")


def run_spider(spider_name: str, output_file: Path, min_items: int = 1) -> Tuple[bool, str]:
    """Run a single spider using Scrapy CLI with atomic file replacement.
    
    Returns (success: bool, error_message: str).
    """
    logger.info(f"Starting spider: {spider_name}")
    
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)
    
    try:
        # Run scrapy crawl with output directed to temp file
        cmd = [
            sys.executable,
            "-m",
            "scrapy",
            "crawl",
            spider_name,
            "-O",
            str(tmp_path),
        ]
        
        result = subprocess.run(
            cmd,
            cwd=str(INDEX_FUNDS_DIR),
            capture_output=True,
            text=True,
            timeout=180,
        )
        
        stderr_tail = "\n".join(result.stderr.strip().splitlines()[-20:]) if result.stderr else ""
        stdout_tail = "\n".join(result.stdout.strip().splitlines()[-20:]) if result.stdout else ""
        log_snippet = stderr_tail or stdout_tail or "No terminal output"
        
        if result.returncode != 0:
            err_msg = f"Spider {spider_name} exited with code {result.returncode}:\n{log_snippet}"
            logger.error(err_msg)
            return False, err_msg
            
        # Validate output JSON
        if not tmp_path.exists() or tmp_path.stat().st_size == 0:
            err_msg = f"Spider {spider_name} produced an empty output file. Scrapy log snippet:\n{log_snippet}"
            logger.error(err_msg)
            return False, err_msg
            
        with open(tmp_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as jde:
                err_msg = f"Spider {spider_name} output invalid JSON: {jde}"
                logger.error(err_msg)
                return False, err_msg
            
        if not isinstance(data, list) or len(data) < min_items:
            count = len(data) if isinstance(data, list) else "not a list"
            err_msg = (
                f"Spider {spider_name} produced invalid or insufficient items: {count} "
                f"(minimum required: {min_items}).\nScrapy log snippet:\n{log_snippet}"
            )
            logger.error(err_msg)
            return False, err_msg
            
        # Atomically replace destination file
        shutil.move(str(tmp_path), str(output_file))
        logger.info(f"Successfully updated {output_file.name} with {len(data)} items.")
        return True, ""
        
    except subprocess.TimeoutExpired:
        err_msg = f"Spider {spider_name} timed out after 180 seconds."
        logger.error(err_msg)
        return False, err_msg
    except Exception as e:
        err_msg = f"Unexpected error running spider {spider_name}: {type(e).__name__}: {e}"
        logger.error(err_msg)
        return False, err_msg
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def run_crawlers() -> Dict[str, Any]:
    """Run all spiders and report summary with full error details."""
    logger.info("Executing End-of-Day Crawl...")
    update_status("running", "Crawl in progress")
    
    results = {}
    errors = {}
    success_all = True
    
    for spider in SPIDERS:
        name = spider["name"]
        ok, err_detail = run_spider(name, spider["output_file"], spider["min_items"])
        if ok:
            results[name] = "success"
        else:
            results[name] = "failed"
            errors[name] = err_detail
            success_all = False
            
    final_status = "success" if success_all else "partial_failure"
    msg = "All spiders crawled successfully" if success_all else f"Failed spiders: {', '.join(errors.keys())}"
    details = {
        "results": results,
        "errors": errors,
    }
    update_status(final_status, msg, details)
    
    logger.info(f"Crawl finished with status: {final_status}")
    if errors:
        for s_name, s_err in errors.items():
            logger.error(f"Error diagnostics for {s_name}:\n{s_err}")
            
    return {
        "status": final_status,
        "message": msg,
        "results": results,
        "errors": errors,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


if __name__ == "__main__":
    result = run_crawlers()
    if result["status"] != "success":
        sys.exit(1)
