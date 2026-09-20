"""Trigger script executed by Render Cron Job (or external scheduler) at 6:00 PM.

Notifies the FastAPI web service via authenticated POST to /api/crawl/run.
If no service URL is available or direct execution is requested, falls back to running
the crawler locally.
"""

import os
import sys
import logging
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def main():
    web_service_url = os.environ.get("WEB_SERVICE_URL", "").strip()
    cron_secret = os.environ.get("CRON_SECRET", "").strip()
    
    if web_service_url:
        if not web_service_url.startswith("http://") and not web_service_url.startswith("https://"):
            web_service_url = f"https://{web_service_url}"
            
        endpoint = f"{web_service_url.rstrip('/')}/api/crawl/run"
        headers = {}
        if cron_secret:
            headers["Authorization"] = f"Bearer {cron_secret}"
            
        logger.info(f"Triggering EOD crawl via Webhook: {endpoint}")
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(endpoint, headers=headers)
                logger.info(f"Response status: {response.status_code}")
                if response.status_code in (200, 202):
                    logger.info("Crawl task successfully initiated.")
                    sys.exit(0)
                else:
                    logger.error(f"Failed to initiate crawl: {response.status_code} - {response.text}")
                    sys.exit(1)
        except Exception as e:
            logger.error(f"Error calling crawl webhook endpoint: {e}")
            logger.info("Falling back to direct crawler execution...")
            from crawler_runner import run_crawlers
            result = run_crawlers()
            sys.exit(0 if result["status"] == "success" else 1)
    else:
        logger.info("No WEB_SERVICE_URL provided. Running crawler directly...")
        from crawler_runner import run_crawlers
        result = run_crawlers()
        sys.exit(0 if result["status"] == "success" else 1)

if __name__ == "__main__":
    main()
