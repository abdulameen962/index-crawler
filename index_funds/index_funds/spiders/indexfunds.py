from scrapy.spiders import CrawlSpider, Rule
import re
from scrapy.linkextractors import LinkExtractor
import scrapy

afrinvest_div_yield = [
    "ACCESSCORP","BERGER","CONOIL","FCMB","GTCO","JBERGER","ZENITHBANK","SFSREIT","MAYBAKER","REDSTAREX","TRIPPLEG",
    "UCAP","WEMABANK","UBA"
]

class AfrinvestDivYieldSpider(scrapy.Spider):
    name = "afribank_div_yield"
    allowed_domains = ["ngxgroup.com"]
    start_urls = [f'https://ngxgroup.com/exchange/data/company-profile/?symbol={symbol}&directory=companydirectory' for symbol in afrinvest_div_yield]
    
    # PROXY_SERVER = "127.0.0.1"
    
    
    rules = (

    )
    
    def parse(self,response):
        yield {
            "title": response.css("td.data strong.CompanyName::text").get(),
            "ticker": response.css("td.data strong.Symbol::text").get(),
            "market_cap": float(response.css("td.data strong.MarketCap::text").get().replace(",","")) if response.css("td.data strong.MarketCap::text").get() else 0,
            "price": float(response.css(".d-dquote-bigContainer .d-dquote-x3::text").get().split("₦")[1].replace(",","")) if response.css(".d-dquote-bigContainer .d-dquote-x3::text").get() else 0,
        }