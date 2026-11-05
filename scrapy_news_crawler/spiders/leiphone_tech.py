"""抓取雷峰网首页最新文章第一页。"""

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import scrapy

from scrapy_news_crawler.items import ScrapyNewsCrawlerItem


class LeiPhoneTechSpider(scrapy.Spider):
    name = "leiphone_tech"
    allowed_domains = ["leiphone.com", "www.leiphone.com"]
    start_urls = ["https://www.leiphone.com/"]

    def parse(self, response):
        # The homepage's latest article list is already the first page. Only
        # follow /latest/index/id/... links; do not request pagination.
        seen = set()
        scheduled = 0
        for anchor in response.css('a[href*="/latest/index/id/"]'):
            url = response.urljoin(anchor.attrib.get("href", "").strip())
            title = self.clean_text(anchor.xpath("string(.)").get())
            host = urlsplit(url).hostname or ""
            if (
                not title
                or host not in {"leiphone.com", "www.leiphone.com"}
                or not urlsplit(url).path.startswith("/latest/index/id/")
                or url in seen
            ):
                continue
            seen.add(url)
            scheduled += 1
            yield response.follow(
                url,
                callback=self.parse_article,
                cb_kwargs={"list_title": title, "rank": scheduled},
            )

        self.logger.info("雷峰网首页最新文章第一页发现 %d 篇，调度 %d 篇", len(seen), scheduled)

    def parse_article(self, response, list_title, rank):
        body = response.css(".lph-article-comView")[:1]
        if not body:
            self.logger.warning("雷峰网正文容器不存在：%s", response.url)
            return

        paragraphs = body.xpath(".//p[not(ancestor::script) and not(ancestor::style)]")
        texts = []
        for node in paragraphs:
            text = self.clean_text(node.xpath(".//text()").getall())
            if text and text != "0":
                texts.append(text)
        content = "\n".join(texts) or self.clean_text(body.xpath("string(.)").get())
        if not content:
            self.logger.warning("雷峰网正文为空：%s", response.url)
            return

        images = []
        for src in body.css("img::attr(src), img::attr(data-src)").getall():
            image_url = response.urljoin(src.strip())
            if image_url.startswith(("http://", "https://")) and image_url not in images:
                images.append(image_url)

        time_text = self.clean_text(response.css(".article-title .msg .time::text").get())
        yield ScrapyNewsCrawlerItem(
            url=response.url,
            title=self.clean_text(response.css("h1.headTit").xpath("string(.)").get()) or list_title,
            content=content,
            image_urls=images,
            source="雷峰网",
            published_at=self.parse_date(time_text),
            crawled_at=datetime.now(timezone.utc).isoformat(),
            board="科技",
            rank=rank,
        )

    @staticmethod
    def clean_text(value):
        if isinstance(value, (list, tuple)):
            value = " ".join(value)
        return " ".join((value or "").split())

    @staticmethod
    def parse_date(value):
        if not value:
            return None
        match = re.search(r"\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}", value)
        if not match:
            return None
        try:
            parsed = datetime.strptime(match.group(), "%Y-%m-%d %H:%M")
            return parsed.replace(tzinfo=timezone(timedelta(hours=8))).astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
