"""中国日报中文网首页左侧图文列表；默认预览，不访问数据库。"""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import scrapy

from scrapy_news_crawler.items import ScrapyNewsCrawlerItem


class ChinadailySpider(scrapy.Spider):
    name = "chinadaily"
    allowed_domains = ["chinadaily.com.cn"]
    start_urls = ["https://cn.chinadaily.com.cn/"]

    def __init__(self, limit=0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.limit = int(limit)
        if self.limit < 0:
            raise ValueError("limit 必须为非负整数，0 表示首页全部图文条目")

    def parse(self, response):
        # Desktop left-hand cards only: no carousel, specials, sidebar, mobile
        # duplicates, pagination or recursively discovered links.
        cards = response.css(".pc .Home_content_Left .Home_content_Item")
        seen = set()
        scheduled = 0
        for card in cards:
            href = card.css(".Home_content_Item_Left a::attr(href)").get()
            cover = card.css(".Home_content_Item_Left img::attr(src)").get()
            title = self.clean_text(card.css("h1 a ::text").getall())
            if not href or not cover or not title:
                continue
            url = response.urljoin(href.strip())
            host = urlsplit(url).hostname or ""
            if not (host == "chinadaily.com.cn" or host.endswith(".chinadaily.com.cn")):
                continue
            if "/a/" not in urlsplit(url).path or url in seen:
                continue
            seen.add(url)
            scheduled += 1
            yield response.follow(
                url,
                callback=self.parse_article,
                cb_kwargs={
                    "list_title": title,
                    "cover_url": response.urljoin(cover.strip()),
                    "board": self.clean_text(card.css(".Home_content_Item_Right > span a ::text").getall()) or "首页图文",
                },
            )
            if self.limit and scheduled >= self.limit:
                break
        self.logger.info("首页左侧发现 %d 个图文卡片，调度 %d 篇（仅打印，不入库）", len(cards), scheduled)

    def parse_article(self, response, list_title, cover_url, board):
        # The page can repeat the same article in desktop/mobile markup.
        body = response.css("#Content")[:1]
        if not body:
            self.logger.warning("正文容器不存在，跳过：%s", response.url)
            return
        paragraphs = body.xpath(
            ".//p[not(ancestor::script) and not(ancestor::style)] | .//figcaption"
        )
        content = "\n".join(
            text for node in paragraphs
            if (text := self.clean_text(node.xpath(".//text()[not(ancestor::script) and not(ancestor::style)]").getall()))
        )
        if not content:
            self.logger.warning("正文为空，跳过：%s", response.url)
            return
        images = []
        for src in [cover_url] + body.css("img::attr(src), img::attr(data-src)").getall():
            url = response.urljoin(src.strip())
            if url.startswith(("http://", "https://")) and url not in images:
                images.append(url)
        published = self.clean_text(response.css(".Artical_Share_Date::text").getall())
        published = published or response.css('meta[name="publishdate"]::attr(content)').get()
        item = ScrapyNewsCrawlerItem(
            url=response.url,
            title=self.clean_text(response.css("h1").xpath("string(.)").getall()[:1]) or list_title,
            content=content,
            image_urls=images,
            source=response.css('meta[name="source"]::attr(content)').get() or "中国日报网",
            published_at=self.parse_date(published),
            crawled_at=datetime.now(timezone.utc).isoformat(),
            board=board,
            rank=None,
        )
        yield item

    @staticmethod
    def clean_text(values):
        return " ".join(" ".join(values).split())

    def parse_date(self, value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.strip())
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            self.logger.warning("无法解析发布时间：%r", value)
            return None
