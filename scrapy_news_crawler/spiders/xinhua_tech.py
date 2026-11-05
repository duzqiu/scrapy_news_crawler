"""抓取新华网科技快讯首页第一页文章。"""

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import scrapy

from scrapy_news_crawler.items import ScrapyNewsCrawlerItem


class XinhuaTechSpider(scrapy.Spider):
    name = "xinhua_tech"
    allowed_domains = ["xinhuanet.com", "news.cn"]
    start_urls = ["https://www.xinhuanet.com/tech/kjkx/index.html"]

    def parse(self, response):
        # Only the current HTML page is selected. No “加载更多” or pagination
        # requests are followed.
        links = response.css('.item a[href$="/c.html"]')
        seen = set()
        scheduled = 0
        for link in links:
            url = response.urljoin(link.attrib.get("href", "").strip())
            title = self.clean_text(link.xpath("string(.)").get())
            host = urlsplit(url).hostname or ""
            if (
                not title
                or host not in {"xinhuanet.com", "www.xinhuanet.com", "news.cn", "www.news.cn"}
                or not urlsplit(url).path.endswith("/c.html")
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

        self.logger.info("新华科技首页第一页发现 %d 篇，调度 %d 篇", len(seen), scheduled)

    def parse_article(self, response, list_title, rank):
        body = response.css("#detailContent")[:1]
        if not body:
            self.logger.warning("新华科技正文容器不存在：%s", response.url)
            return

        paragraphs = body.xpath(".//p[not(ancestor::script) and not(ancestor::style)]")
        content = "\n".join(
            text
            for node in paragraphs
            if (text := self.clean_text(node.xpath(".//text()").getall()))
        ) or self.clean_text(body.xpath("string(.)").get())
        if not content:
            self.logger.warning("新华科技正文为空：%s", response.url)
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
        yield ScrapyNewsCrawlerItem(
            url=response.url,
            title=self.clean_text(response.css("h1").xpath("string(.)").get()) or list_title,
            content=content,
            image_urls=images,
            source="新华网科技",
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

    def parse_date(self, value):
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.strip())
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            self.logger.warning("无法解析新华科技发布时间：%r", value)
            return None
