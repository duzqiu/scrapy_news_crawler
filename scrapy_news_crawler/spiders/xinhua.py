"""抓取新华网首页中部“要闻聚焦”栏目。"""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
import json

import scrapy

from scrapy_news_crawler.items import ScrapyNewsCrawlerItem


class XinhuaSpider(scrapy.Spider):
    name = "xinhua"
    allowed_domains = ["xinhuanet.com", "news.cn"]
    start_urls = ["https://www.xinhuanet.com/"]
    # Preview only: do not write the hot-list records to PostgreSQL or Redis.
    # custom_settings = {
    #     "ITEM_PIPELINES": {},
    # }

    def __init__(self, limit=0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit = int(limit)
        if self.limit < 0:
            raise ValueError("limit 必须为非负整数，0 表示抓取全部要闻聚焦文章")

    def parse(self, response):
        # Restrict selection to the homepage's middle #depth section whose
        # heading is exactly “要闻聚焦”; do not follow other homepage links.
        section = response.xpath(
            '//div[@id="depth"]//div[contains(@class,"part")][.//div[@class="name" and normalize-space()="要闻聚焦"]]'
        )[:1]
        if not section:
            self.logger.warning("没有找到新华网首页“要闻聚焦”栏目")
            return

        links = section.css(".depth-cont a[href]")
        seen = set()
        scheduled = 0
        for link in links:
            href = link.attrib.get("href", "").strip()
            title = self.clean_text(link.xpath("string(.)").get())
            if not href or not title:
                continue
            url = response.urljoin(href)
            host = urlsplit(url).hostname or ""
            if host not in {"xinhuanet.com", "www.xinhuanet.com", "news.cn", "www.news.cn"}:
                continue
            if not urlsplit(url).path.endswith("/c.html") or url in seen:
                continue
            seen.add(url)
            scheduled += 1
            yield response.follow(
                url,
                callback=self.parse_article,
                cb_kwargs={"list_title": title, "rank": scheduled},
            )
            if self.limit and scheduled >= self.limit:
                break

        self.logger.info("新华网“要闻聚焦”发现 %d 篇，调度 %d 篇", len(seen), scheduled)

    def parse_article(self, response, list_title, rank):
        body = response.css("#detailContent")[:1]
        if not body:
            self.logger.warning("新华网正文容器不存在：%s", response.url)
            return

        paragraphs = body.xpath(
            ".//p[not(ancestor::script) and not(ancestor::style)]"
        )
        content = "\n".join(
            text
            for node in paragraphs
            if (text := self.clean_text(node.xpath(".//text()").getall()))
        )
        if not content:
            content = self.clean_text(body.xpath("string(.)").get())
        if not content:
            self.logger.warning("新华网正文为空：%s", response.url)
            return

        images = []
        for src in body.css("img::attr(src), img::attr(data-src)").getall():
            image_url = response.urljoin(src.strip())
            if image_url.startswith(("http://", "https://")) and image_url not in images:
                images.append(image_url)

        published = (
            response.css('meta[name="publishdate"]::attr(content)').get()
            or response.css('meta[name="pubtime"]::attr(content)').get()
        )
        item = ScrapyNewsCrawlerItem(
            url=response.url,
            title=self.clean_text(response.css("h1").xpath("string(.)").get()) or list_title,
            content=content,
            image_urls=images,
            source="新华网",
            published_at=self.parse_date(published),
            crawled_at=datetime.now(timezone.utc).isoformat(),
            board="要闻聚焦",
            rank=rank,
        )
        # This Spider is currently a preview-only exception: print the full
        # detail content and keep the Pipeline disabled, so nothing is stored.
        print(json.dumps(dict(item), ensure_ascii=False, indent=2), flush=True)
        yield item

    @staticmethod
    def clean_text(value):
        if isinstance(value, (list, tuple)):
            value = " ".join(value)
        return " ".join((value or "").split())

    def parse_date(self, value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.strip())
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            self.logger.warning("无法解析新华网发布时间：%r", value)
            return None
