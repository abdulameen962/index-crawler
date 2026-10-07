import json
import re
import scrapy
from scrapy.spiders import CrawlSpider, Rule


def clean_number(val):
    """Clean numeric values (handles strings with currency symbols, commas, or empty values)."""
    if val is None or val == "" or val in ("—", "-", "–", "N/A", "n/a"):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    cleaned = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0


def get_field_by_th(response, keywords):
    """Extract table cell text from wpDataTable/ngx-dw-table by matching header label."""
    for kw in keywords:
        nodes = response.xpath(
            f"//tr[th[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{kw.lower()}')]]/td//text()"
        ).getall()
        if nodes:
            val = " ".join("".join(nodes).split()).strip()
            if val and val not in ("—", "-", "–", "N/A", "n/a"):
                return val
    return None


def get_price(response):
    """Extract latest stock price from quote banner or datablock."""
    # 1. Main quote banner .d-dquote-x3
    raw = response.css(".d-dquote-bigContainer .d-dquote-x3::text").get()
    if not raw:
        raw = response.css(".d-dquote-x3::text").get()

    # 2. Datablock Prev Close
    if not raw or not re.sub(r"[^\d.]", "", raw):
        raw = response.xpath(
            "//div[contains(@class, 'd-dquote-datablock')][span[contains(., 'Prev Close')]]/span[contains(@class, 'd-dquote-datablock-value')]/text()"
        ).get()

    # 3. Datablock Open
    if not raw or not re.sub(r"[^\d.]", "", raw):
        raw = response.xpath(
            "//div[contains(@class, 'd-dquote-datablock')][span[contains(., 'Open')]]/span[contains(@class, 'd-dquote-datablock-value')]/text()"
        ).get()

    # 4. Table Official close / open fallback
    if not raw or not re.sub(r"[^\d.]", "", raw):
        raw = get_field_by_th(response, ["official close", "official open"])

    return clean_number(raw)


def get_market_cap(response):
    """Extract market cap, falling back to share_price * outstanding_shares if needed."""
    raw = get_field_by_th(response, ["market cap"])
    if not raw:
        raw = response.css("td.data strong.MarketCap::text").get()

    market_cap = clean_number(raw)

    if market_cap == 0.0:
        share_price = get_price(response)
        raw_shares = get_field_by_th(response, ["shares outstanding"])
        if not raw_shares:
            raw_shares = response.css("td.data strong.SharesOutstanding::text").get()
        shares = clean_number(raw_shares)
        if shares > 0 and share_price > 0:
            market_cap = round(share_price * shares, 2)

    return market_cap


def extract_symbol_and_name(response, default_symbol=""):
    """Extract ticker symbol and company name with multiple robust fallbacks."""
    symbol = get_field_by_th(response, ["ticker symbol", "ticker", "symbol"])
    if not symbol:
        symbol = response.css("td.data strong.Symbol::text").get()
    if not symbol:
        header_text = "".join(response.css(".d-dquote-symbol *::text").getall())
        m = re.search(r"\(\s*([A-Za-z0-9_-]+)\s*\)", header_text)
        if m:
            symbol = m.group(1)
    if not symbol and hasattr(response, "url"):
        m = re.search(r"symbol=([A-Za-z0-9_-]+)", response.url)
        symbol = m.group(1) if m else ""
    if not symbol:
        symbol = default_symbol

    company_name = get_field_by_th(response, ["company name"])
    if not company_name:
        company_name = response.css("td.data strong.CompanyName::text").get()
    if not company_name:
        company_name = response.css(".d-dquote-symbol span:first-child::text").get()
    if not company_name and symbol:
        company_name = f"{symbol} PLC ({symbol})"

    symbol = symbol.strip() if symbol else ""
    company_name = company_name.strip() if company_name else symbol

    return symbol, company_name


afrinvest_div_yield = [
    "ACCESSCORP", "FCMB", "GTCO", "JBERGER", "ZENITHBANK", "OKOMUOIL",
    "UCAP", "VITAFOAM", "WEMABANK", "UBA", "DANGCEM"
]

oil_and_gas = [
    "CONOIL", "ETERNA", "JAPAULGOLD", "OANDO", "TOTAL", "SEPLAT", "ARADEL"
]


def get_ngx_headers(symbol: str) -> dict:
    """Build standard browser headers matching NGX company directory requests."""
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": f"https://ngxgroup.com/exchange/data/company-profile/?symbol={symbol}&directory=companydirectory",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


class BaseNgxSpider(scrapy.Spider):
    allowed_domains = ["ngxgroup.com"]
    symbols = []

    def start_requests(self):
        for symbol in self.symbols:
            summary_url = (
                f"https://ngxgroup.com/wp-json/ngx-data-widgets/v1/company/summary"
                f"?symbol={symbol}&directory=companydirectory"
            )
            yield scrapy.Request(
                summary_url,
                callback=self.parse_summary,
                meta={"symbol": symbol},
                headers=get_ngx_headers(symbol),
            )

    def parse_summary(self, response):
        symbol = response.meta.get("symbol", "")
        if response.status != 200:
            self.logger.error(
                f"[{symbol}] Non-200 HTTP status ({response.status}) on summary endpoint: {response.text[:250]}"
            )
            return

        try:
            data = json.loads(response.text)
        except Exception as exc:
            self.logger.error(
                f"[{symbol}] Non-JSON summary response ({exc}). Snippet: {response.text[:250]}"
            )
            return

        if not isinstance(data, dict):
            self.logger.error(f"[{symbol}] Summary payload is not a dict: {data}")
            return

        price = clean_number(data.get("StockPriceCur"))
        if price == 0.0:
            price = clean_number(data.get("PrevClose"))
        if price == 0.0:
            price = clean_number(data.get("OpenPrice"))

        company_name = data.get("CompanyName")
        ticker = data.get("Symbol") or symbol

        if not company_name or price <= 0.0:
            self.logger.warning(
                f"[{symbol}] Summary missing valid name or positive price: name='{company_name}', price={price}. Payload: {data}"
            )
            return

        trading_url = (
            f"https://ngxgroup.com/wp-json/ngx-data-widgets/v1/company/trading"
            f"?symbol={symbol}&directory=companydirectory"
        )
        yield scrapy.Request(
            trading_url,
            callback=self.parse_trading,
            meta={
                "symbol": symbol,
                "item": {
                    "title": str(company_name).strip(),
                    "ticker": str(ticker).strip(),
                    "price": price,
                },
            },
            headers=get_ngx_headers(symbol),
        )

    def parse_trading(self, response):
        item = response.meta.get("item", {})
        symbol = response.meta.get("symbol", "")
        if response.status != 200:
            self.logger.error(
                f"[{symbol}] Non-200 HTTP status ({response.status}) on trading endpoint: {response.text[:250]}"
            )
            return

        try:
            data = json.loads(response.text)
        except Exception as exc:
            self.logger.error(
                f"[{symbol}] Non-JSON trading response ({exc}). Snippet: {response.text[:250]}"
            )
            return

        if not isinstance(data, dict):
            self.logger.error(f"[{symbol}] Trading payload is not a dict: {data}")
            return

        market_cap = clean_number(data.get("MarketCap"))
        if market_cap == 0.0:
            shares = clean_number(data.get("SharesOutstanding"))
            price = item.get("price", 0.0)
            if shares > 0 and price > 0:
                market_cap = round(price * shares, 2)

        if not item.get("title") and data.get("CompanyName"):
            item["title"] = str(data.get("CompanyName")).strip()
        if not item.get("ticker") and data.get("Symbol"):
            item["ticker"] = str(data.get("Symbol")).strip()

        if market_cap <= 0.0:
            self.logger.warning(
                f"[{symbol}] Could not determine valid market_cap for {symbol}. Trading payload: {data}"
            )
            return

        item["market_cap"] = market_cap
        yield item

    def parse(self, response):
        """Fallback for direct HTML responses."""
        symbol, company_name = extract_symbol_and_name(response)
        yield {
            "title": company_name,
            "ticker": symbol,
            "market_cap": get_market_cap(response),
            "price": get_price(response),
        }


class AfrinvestDivYieldSpider(BaseNgxSpider):
    name = "afribank_div_yield"
    symbols = afrinvest_div_yield
    start_urls = [
        f"https://ngxgroup.com/exchange/data/company-profile/?symbol={symbol}&directory=companydirectory"
        for symbol in afrinvest_div_yield
    ]


class OilandGas(BaseNgxSpider):
    name = "oil_and_gas"
    symbols = oil_and_gas
    start_urls = [
        f"https://ngxgroup.com/exchange/data/company-profile/?symbol={symbol}&directory=companydirectory"
        for symbol in oil_and_gas
    ]

