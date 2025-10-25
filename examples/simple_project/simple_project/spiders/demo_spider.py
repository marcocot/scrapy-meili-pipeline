from __future__ import annotations

from urllib.parse import urljoin
from typing import Iterator
from uuid import uuid4

import scrapy
from scrapy.spiders import CrawlSpider


class DemoSpider(CrawlSpider):
    """
    Demo spider for the webscraper.io test site:
    https://webscraper.io/test-sites/e-commerce/allinone

    Strategy:
    - Start from the "allinone" landing page and follow internal links.
    - Parse product tiles (listing cards) wherever present, without visiting product detail pages.
    - Yield normalized documents suitable for Meilisearch indexing.
    """

    name = "demo"
    allowed_domains = ["webscraper.io"]
    start_urls = ["https://webscraper.io/test-sites/e-commerce/allinone"]

    custom_settings = {
        # You can override batch size if you want to see more flush cycles:
        # "MEILI_BATCH_SIZE": 3,
        # Respectful crawl
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_DELAY": 0.5,
        "CONCURRENT_REQUESTS": 8,
        "LOG_LEVEL": "INFO",
    }

    def parse_start_url(self, response: scrapy.http.Response) -> Iterator[scrapy.Request] | Iterator[dict]:
        # Handle product tiles on the landing page too (if any)
        yield from self.parse_listing(response)

    def parse_listing(self, response: scrapy.http.Response) -> Iterator[dict]:
        """
        Parse product tiles ("cards") from listing pages.
        """

        tiles = response.css(".thumbnail")
        for card in tiles:
            title = card.css("a.title::attr(title)").get() or card.css("a.title::text").get() or ""
            href = card.css("a.title::attr(href)").get()
            url = urljoin(response.url, href) if href else response.url

            doc = {
                "id": str(uuid4()),  # just for demo purposes
                "url": url,
                "title": title.strip(),
                "source": "webscraper.io-allinone",
            }

            yield doc
