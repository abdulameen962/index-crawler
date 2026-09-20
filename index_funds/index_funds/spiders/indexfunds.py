from scrapy.spiders import CrawlSpider, Rule
import re
from scrapy.linkextractors import LinkExtractor
import scrapy
def get_price(response):
    raw = response.css(".d-dquote-bigContainer .d-dquote-x3::text").get()
    if not raw:
        return 0.0
    cleaned = re.sub(r"[^\d.]", "", raw)
    try:
        return float(cleaned) if cleaned else 0.0
    except (ValueError, TypeError):
        return 0.0


def get_market_cap(response):
    raw = response.css("td.data strong.MarketCap::text").get()
    market_cap = 0.0
    if raw:
        cleaned = re.sub(r"[^\d.]", "", raw)
        try:
            market_cap = float(cleaned) if cleaned else 0.0
        except (ValueError, TypeError):
            market_cap = 0.0

    if market_cap == 0.0:
        share_price = get_price(response)
        raw_shares = response.css("td.data strong.SharesOutstanding::text").get()
        if raw_shares:
            cleaned_shares = re.sub(r"[^\d.]", "", raw_shares)
            try:
                outstanding_shares = float(cleaned_shares) if cleaned_shares else 0.0
                market_cap = round(share_price * outstanding_shares, 2)
            except (ValueError, TypeError):
                pass

    return market_cap


afrinvest_div_yield = [
    "ACCESSCORP", "FCMB", "GTCO", "JBERGER", "ZENITHBANK", "OKOMUOIL",
    "UCAP", "VITAFOAM", "WEMABANK", "UBA", "DANGCEM"
]

oil_and_gas = [
    "CONOIL", "ETERNA", "JAPAULGOLD", "OANDO", "TOTAL", "SEPLAT", "ARADEL"
]


class AfrinvestDivYieldSpider(scrapy.Spider):
    name = "afribank_div_yield"
    allowed_domains = ["ngxgroup.com"]
    start_urls = [
        f"https://ngxgroup.com/exchange/data/company-profile/?symbol={symbol}&directory=companydirectory"
        for symbol in afrinvest_div_yield
    ]

    def parse(self, response):
        symbol = response.css("td.data strong.Symbol::text").get()
        if not symbol:
            m = re.search(r"symbol=([A-Za-z0-9_-]+)", response.url)
            symbol = m.group(1) if m else ""

        company_name = response.css("td.data strong.CompanyName::text").get()
        if not company_name:
            company_name = f"{symbol} PLC ({symbol})"

        yield {
            "title": company_name.strip() if company_name else symbol,
            "ticker": symbol.strip() if symbol else "",
            "market_cap": get_market_cap(response),
            "price": get_price(response),
        }


class OilandGas(scrapy.Spider):
    name = "oil_and_gas"
    allowed_domains = ["ngxgroup.com"]
    start_urls = [
        f"https://ngxgroup.com/exchange/data/company-profile/?symbol={symbol}&directory=companydirectory"
        for symbol in oil_and_gas
    ]

    def parse(self, response):
        symbol = response.css("td.data strong.Symbol::text").get()
        if not symbol:
            m = re.search(r"symbol=([A-Za-z0-9_-]+)", response.url)
            symbol = m.group(1) if m else ""

        company_name = response.css("td.data strong.CompanyName::text").get()
        if not company_name:
            company_name = f"{symbol} PLC ({symbol})"

        yield {
            "title": company_name.strip() if company_name else symbol,
            "ticker": symbol.strip() if symbol else "",
            "market_cap": get_market_cap(response),
            "price": get_price(response),
        }