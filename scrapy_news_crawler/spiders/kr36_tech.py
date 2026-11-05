"""抓取 36 氪科技频道第一页文章。"""

from datetime import datetime, timezone
from urllib.parse import urlsplit

import scrapy

from scrapy_news_crawler.items import ScrapyNewsCrawlerItem


class Kr36TechSpider(scrapy.Spider):
    name = "36kr_tech"
    allowed_domains = ["36kr.com", "www.36kr.com"]
    start_urls = ["https://www.36kr.com/information/technology/"]

    def parse(self, response):
        # Only links rendered on the current first page are followed. Do not
        # request pagination or any load-more endpoint.
        seen = set()
        scheduled = 0
        for anchor in response.css('a[href^="/p/"]'):
            href = anchor.attrib.get("href", "").strip()
            url = response.urljoin(href)
            title = self.clean_text(anchor.xpath("string(.)").get())
            host = urlsplit(url).hostname or ""
            if (
                not title
                or host not in {"36kr.com", "www.36kr.com"}
                or not urlsplit(url).path.startswith("/p/")
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

        self.logger.info("36氪科技第一页发现 %d 篇，调度 %d 篇", len(seen), scheduled)

    def parse_article(self, response, list_title, rank):
        body = response.css(".articleDetailContent")[:1]
        if not body:
            self.logger.warning("36氪正文容器不存在：%s", response.url)
            return

        paragraphs = body.xpath(".//p[not(ancestor::script) and not(ancestor::style)]")
        content = "\n".join(
            text
            for node in paragraphs
            if (text := self.clean_text(node.xpath(".//text()").getall()))
        ) or self.clean_text(body.xpath("string(.)").get())
        if not content:
            self.logger.warning("36氪正文为空：%s", response.url)
            return

        images = []
        for src in body.css("img::attr(src), img::attr(data-src)").getall():
            image_url = response.urljoin(src.strip())
            if image_url.startswith(("http://", "https://")) and image_url not in images:
                images.append(image_url)

        published = response.css('meta[property="article:published_time"]::attr(content)').get()
        yield ScrapyNewsCrawlerItem(
            url=response.url,
            title=self.clean_text(response.css("h1").xpath("string(.)").get()) or list_title,
            content=content,
            image_urls=images,
            source="36氪",
            published_at=self.parse_date(published),
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
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
