"""FastAPI Application for NGX Index Fund Replicator.

Serves the single-page Dribbble trading terminal,
provides API endpoints for portfolio replication calculations,
SEO routes (robots.txt, sitemap.xml), and manages background
EOD crawler tasks with 4:00 PM - 8:50 AM WAT time-window locking.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from fastapi import FastAPI, HTTPException, BackgroundTasks, Header, Depends, status, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from main import replicate_index_fund_detailed
import crawler_runner

BASE_DIR = Path(__file__).resolve().parent
INDEX_FUNDS_DIR = BASE_DIR / "index_funds"
STATIC_DIR = BASE_DIR / "static"

# West Africa Time (WAT / UTC+1)
WAT = timezone(timedelta(hours=1))

FUNDS_REGISTRY = {
    "oil_gas": {
        "id": "oil_gas",
        "name": "NGX Oil & Gas Index",
        "badge": "🛢️ Oil & Gas",
        "file": INDEX_FUNDS_DIR / "oil_gas.json",
        "description": "Leading petroleum and energy equities listed on the Nigerian Exchange.",
    },
    "afribank": {
        "id": "afribank",
        "name": "Afrinvest Div Yield Index",
        "badge": "📈 Div Yield",
        "file": INDEX_FUNDS_DIR / "afribank.json",
        "description": "High dividend-yielding equities across banking, industrial, and consumer goods.",
    },
}

app = FastAPI(
    title="NGX Index Fund Replicator",
    description="Calculate exact share allocations and fees for replicating NGX index funds.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static assets
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def is_market_hours_wat() -> Tuple[bool, str]:
    """Check if current time is within NGX market trading hours (08:50 AM to 04:00 PM WAT).
    
    Returns (is_market_in_session, status_message).
    Allowed manual sync window: 4:00 PM - 8:50 AM WAT (16:00 - 23:59, 00:00 - 08:50).
    """
    now_wat = datetime.now(WAT)
    current_time_minutes = now_wat.hour * 60 + now_wat.minute
    market_open_minutes = 8 * 60 + 50   # 08:50
    market_close_minutes = 16 * 60       # 16:00
    
    if market_open_minutes <= current_time_minutes < market_close_minutes:
        return True, "Market is in session (08:50 AM - 04:00 PM WAT). Price updates are locked to protect clean EOD data from daytime null ticks. Available post-market at 4:00 PM."
    return False, "Market is closed. End-of-day price updates are unlocked and available."


class CalculationRequest(BaseModel):
    fund_id: str = Field(default="oil_gas", description="Index fund ID ('oil_gas' or 'afribank')")
    investment_amount: float = Field(default=50000.0, ge=0.0, description="Capital to invest in NGN")
    transaction_cost_rate: float = Field(default=0.03, ge=0.0, le=0.5, description="Transaction fee rate (e.g. 0.03 for 3%)")
    cap_percentage: float = Field(default=0.15, ge=0.01, le=1.0, description="Maximum single equity weight cap (e.g. 0.15 for 15%)")


def verify_cron_token_or_time_window(authorization: Optional[str] = Header(None)) -> bool:
    """Verify authorization or check if within allowed 4:00 PM - 8:50 AM WAT window."""
    configured_secret = os.environ.get("CRON_SECRET", "").strip()
    
    # If valid cron secret provided, allow execution regardless of time
    if configured_secret and authorization:
        token = authorization.replace("Bearer ", "").strip()
        if token == configured_secret:
            return True
            
    # Otherwise, enforce the time-window lock (must be outside 08:50 AM - 04:00 PM WAT)
    is_locked, msg = is_market_hours_wat()
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=msg,
        )
    return True


@app.get("/")
def get_dashboard():
    """Serve the single-page frontend application."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Dashboard frontend not found")
    return FileResponse(str(index_file))


@app.get("/favicon.ico", include_in_schema=False)
def get_favicon():
    """Serve the favicon."""
    ico_file = STATIC_DIR / "favicon.ico"
    if ico_file.exists():
        return FileResponse(str(ico_file), media_type="image/x-icon")
    return Response(status_code=204)


@app.get("/robots.txt", response_class=PlainTextResponse)
def get_robots_txt():
    """Serve robots.txt for search engines."""
    robots_file = STATIC_DIR / "robots.txt"
    if robots_file.exists():
        return robots_file.read_text(encoding="utf-8")
    return "User-agent: *\nAllow: /\nSitemap: /sitemap.xml\n"


@app.get("/sitemap.xml")
def get_sitemap_xml():
    """Serve sitemap.xml for search engines."""
    sitemap_file = STATIC_DIR / "sitemap.xml"
    if sitemap_file.exists():
        return Response(content=sitemap_file.read_text(encoding="utf-8"), media_type="application/xml")
    return Response(content="<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">\n  <url><loc>/</loc><priority>1.0</priority></url>\n</urlset>", media_type="application/xml")


@app.get("/api/market-status")
def get_market_status():
    """Return whether the manual price sync button is locked or accessible."""
    now_wat = datetime.now(WAT)
    is_locked, message = is_market_hours_wat()
    return {
        "is_locked": is_locked,
        "can_sync": not is_locked,
        "current_time_wat": now_wat.strftime("%I:%M %p WAT"),
        "message": message,
        "allowed_hours": "04:00 PM - 08:50 AM WAT",
        "locked_hours": "08:50 AM - 04:00 PM WAT",
    }


@app.get("/api/funds")
def list_funds():
    """List available index funds with metadata and last modified timestamps."""
    funds_list = []
    for fund_id, meta in FUNDS_REGISTRY.items():
        file_path: Path = meta["file"]
        equities_count = 0
        last_updated_iso = None
        sample_tickers = []
        
        if file_path.exists():
            try:
                stat = file_path.stat()
                last_updated_iso = datetime.fromtimestamp(stat.st_mtime).isoformat()
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        equities_count = len(data)
                        sample_tickers = [item.get("ticker", "") for item in data[:5] if item.get("ticker")]
            except Exception:
                pass
                
        funds_list.append({
            "id": fund_id,
            "name": meta["name"],
            "badge": meta["badge"],
            "description": meta["description"],
            "equities_count": equities_count,
            "last_updated": last_updated_iso,
            "sample_tickers": sample_tickers,
        })
    return {"funds": funds_list}


@app.post("/api/calculate")
def calculate_portfolio(req: CalculationRequest):
    """Calculate share allocation and costs for a chosen index fund."""
    fund = FUNDS_REGISTRY.get(req.fund_id)
    if not fund:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown fund_id '{req.fund_id}'. Supported funds: {list(FUNDS_REGISTRY.keys())}",
        )
    
    file_path: Path = fund["file"]
    if not file_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Fund data file missing: {file_path.name}",
        )
        
    try:
        result = replicate_index_fund_detailed(
            fund_file=str(file_path),
            investment_amount=req.investment_amount,
            transaction_cost_rate=req.transaction_cost_rate,
            cap_percentage=req.cap_percentage,
        )
        result["fund_id"] = req.fund_id
        result["fund_name"] = fund["name"]
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/crawl/run", status_code=status.HTTP_202_ACCEPTED)
def trigger_crawl(background_tasks: BackgroundTasks, _auth: bool = Depends(verify_cron_token_or_time_window)):
    """Trigger background crawler task to fetch latest NGX prices.
    
    Allowed outside 8:50 AM - 4:00 PM WAT, or anytime with valid CRON_SECRET.
    """
    background_tasks.add_task(crawler_runner.run_crawlers)
    return {
        "status": "accepted",
        "message": "End-of-day crawler initiated in the background.",
        "triggered_at": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/crawl/status")
def get_crawl_status():
    """Retrieve the status of the most recent EOD crawl."""
    status_file = crawler_runner.STATUS_FILE
    if status_file.exists():
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {"status": "unknown", "error": str(e)}
            
    return {
        "status": "idle",
        "message": "No scheduled crawl executed yet. Using packaged EOD datasets.",
        "timestamp": None,
    }
