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
        "symbols": [
            "CONOIL", "ETERNA", "JAPAULGOLD", "OANDO", "TOTAL", "SEPLAT", "ARADEL"
        ],
        "output_file": INDEX_FUNDS_DIR / "oil_gas.json",
        "min_items": 3,
    },
    {
        "name": "afribank_div_yield",
        "symbols": [
            "ACCESSCORP", "FCMB", "GTCO", "JBERGER", "ZENITHBANK", "OKOMUOIL",
            "UCAP", "VITAFOAM", "WEMABANK", "UBA", "DANGCEM"
        ],
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


def validate_dataset(data: Any, min_items: int, spider_name: str) -> Tuple[bool, str]:
    """Validate that crawled data contains genuine non-zero constituent information."""
    if not isinstance(data, list):
        return False, f"Expected list of items, got {type(data).__name__}"
    if len(data) < min_items:
        return False, f"Insufficient items ({len(data)} < {min_items})"

    zero_price_items = []
    zero_mcap_items = []

    for item in data:
        ticker = item.get("ticker", "UNKNOWN")
        price = item.get("price", 0.0)
        mcap = item.get("market_cap", 0.0)
        title = item.get("title", "")

        if not isinstance(price, (int, float)) or price <= 0:
            zero_price_items.append(ticker)
        if not isinstance(mcap, (int, float)) or mcap <= 0:
            zero_mcap_items.append(ticker)

    if zero_price_items:
        return False, f"Data quality check failed: {len(zero_price_items)} items have zero/missing price: {zero_price_items}"
    if zero_mcap_items:
        return False, f"Data quality check failed: {len(zero_mcap_items)} items have zero/missing market_cap: {zero_mcap_items}"

    return True, ""


def write_atomic_json(target_path: Path, data: list) -> None:
    """Safely and atomically write data to target JSON file."""
    temp_target = target_path.with_suffix(".tmp.json")
    with open(temp_target, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    temp_target.replace(target_path)


def fetch_via_httpx(symbols: list, min_items: int) -> Tuple[bool, list, str]:
    """Fallback fetcher using httpx with complete browser headers and session handling."""
    logger.info(f"Attempting fallback HTTPX crawler for {len(symbols)} symbols...")
    try:
        import httpx
    except ImportError:
        return False, [], "httpx library not available for fallback"

    # Import clean_number from spider module
    sys.path.insert(0, str(INDEX_FUNDS_DIR))
    try:
        from index_funds.spiders.indexfunds import clean_number
    except ImportError:
        import re
        def clean_number(val):
            if val is None or val == "" or val in ("—", "-", "–", "N/A", "n/a"):
                return 0.0
            if isinstance(val, (int, float)):
                return float(val)
            cleaned = re.sub(r"[^\d.]", "", str(val))
            try:
                return float(cleaned) if cleaned else 0.0
            except (ValueError, TypeError):
                return 0.0

    browser_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

    results = []
    try:
        with httpx.Client(headers=browser_headers, follow_redirects=True, timeout=25.0) as client:
            for symbol in symbols:
                profile_url = f"https://ngxgroup.com/exchange/data/company-profile/?symbol={symbol}&directory=companydirectory"
                req_headers = {**browser_headers, "Referer": profile_url}

                # 1. Summary endpoint
                summary_url = f"https://ngxgroup.com/wp-json/ngx-data-widgets/v1/company/summary?symbol={symbol}&directory=companydirectory"
                try:
                    r_sum = client.get(summary_url, headers=req_headers)
                    if r_sum.status_code != 200:
                        logger.warning(f"[HTTPX] {symbol} summary returned {r_sum.status_code}")
                        continue
                    sum_data = r_sum.json()
                except Exception as e:
                    logger.warning(f"[HTTPX] Error fetching summary for {symbol}: {e}")
                    continue

                price = clean_number(sum_data.get("StockPriceCur"))
                if price == 0.0:
                    price = clean_number(sum_data.get("PrevClose"))
                if price == 0.0:
                    price = clean_number(sum_data.get("OpenPrice"))

                company_name = sum_data.get("CompanyName")
                ticker = sum_data.get("Symbol") or symbol

                if not company_name or price <= 0:
                    logger.warning(f"[HTTPX] Incomplete summary for {symbol}: price={price}, company={company_name}")
                    continue

                # 2. Trading endpoint
                trading_url = f"https://ngxgroup.com/wp-json/ngx-data-widgets/v1/company/trading?symbol={symbol}&directory=companydirectory"
                try:
                    r_trade = client.get(trading_url, headers=req_headers)
                    if r_trade.status_code != 200:
                        logger.warning(f"[HTTPX] {symbol} trading returned {r_trade.status_code}")
                        continue
                    trade_data = r_trade.json()
                except Exception as e:
                    logger.warning(f"[HTTPX] Error fetching trading for {symbol}: {e}")
                    continue

                market_cap = clean_number(trade_data.get("MarketCap"))
                if market_cap == 0.0:
                    shares = clean_number(trade_data.get("SharesOutstanding"))
                    if shares > 0 and price > 0:
                        market_cap = round(price * shares, 2)

                if market_cap <= 0:
                    logger.warning(f"[HTTPX] Zero market cap for {symbol}")
                    continue

                results.append({
                    "title": str(company_name).strip(),
                    "ticker": str(ticker).strip(),
                    "price": price,
                    "market_cap": market_cap,
                })

        valid, err_msg = validate_dataset(results, min_items, "httpx_fallback")
        if not valid:
            return False, results, f"HTTPX fallback collected data failed validation: {err_msg}"

        return True, results, ""
    except Exception as e:
        return False, [], f"HTTPX fallback failed with error: {e}"


def run_spider(spider_config: Dict[str, Any]) -> Tuple[bool, str]:
    """Run a single spider using Scrapy CLI with atomic file replacement and HTTPX fallback.
    
    Guarantees that destination files are NEVER overwritten with zero or invalid data.
    """
    spider_name = spider_config["name"]
    output_file = spider_config["output_file"]
    min_items = spider_config["min_items"]
    symbols = spider_config["symbols"]

    logger.info(f"Starting spider: {spider_name}")
    
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)
    
    scrapy_ok = False
    scrapy_err = ""
    scrapy_data = None

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
            scrapy_err = f"Spider {spider_name} exited with code {result.returncode}:\n{log_snippet}"
            logger.warning(scrapy_err)
        elif not tmp_path.exists() or tmp_path.stat().st_size == 0:
            scrapy_err = f"Spider {spider_name} produced an empty output file.\n{log_snippet}"
            logger.warning(scrapy_err)
        else:
            with open(tmp_path, "r", encoding="utf-8") as f:
                try:
                    scrapy_data = json.load(f)
                except json.JSONDecodeError as jde:
                    scrapy_err = f"Spider {spider_name} output invalid JSON: {jde}"
                    logger.warning(scrapy_err)

            if scrapy_data is not None:
                valid, val_err = validate_dataset(scrapy_data, min_items, spider_name)
                if valid:
                    scrapy_ok = True
                else:
                    scrapy_err = f"Spider {spider_name} data failed quality check: {val_err}"
                    logger.warning(scrapy_err)

    except subprocess.TimeoutExpired:
        scrapy_err = f"Spider {spider_name} timed out after 180 seconds."
        logger.warning(scrapy_err)
    except Exception as e:
        scrapy_err = f"Unexpected error running Scrapy spider {spider_name}: {e}"
        logger.warning(scrapy_err)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass

    if scrapy_ok and scrapy_data:
        write_atomic_json(output_file, scrapy_data)
        logger.info(f"Successfully updated {output_file.name} via Scrapy with {len(scrapy_data)} valid items.")
        return True, ""

    # Scrapy failed or produced invalid/zero data -> Activate HTTPX fallback
    logger.info(f"Scrapy did not yield valid data for {spider_name}. Reason: {scrapy_err}. Triggering HTTPX fallback...")
    httpx_ok, httpx_data, httpx_err = fetch_via_httpx(symbols, min_items)
    if httpx_ok and httpx_data:
        write_atomic_json(output_file, httpx_data)
        logger.info(f"Successfully updated {output_file.name} via HTTPX fallback with {len(httpx_data)} valid items.")
        return True, ""

    # Both failed -> Protect existing dataset, do NOT overwrite with zeroes
    full_err = f"Both Scrapy and HTTPX fallback failed for {spider_name}.\nScrapy error: {scrapy_err}\nHTTPX error: {httpx_err}"
    logger.error(full_err)
    logger.error(f"Preserved existing {output_file.name} to prevent data loss.")
    return False, full_err


def run_crawlers() -> Dict[str, Any]:
    """Run all spiders and report summary with full error details."""
    logger.info("Executing End-of-Day Crawl...")
    update_status("running", "Crawl in progress")
    
    results = {}
    errors = {}
    success_all = True
    
    for spider in SPIDERS:
        name = spider["name"]
        ok, err_detail = run_spider(spider)
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
