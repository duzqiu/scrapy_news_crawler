"""抓取新浪科技首页“热点”列表前 20 条文章。"""

from datetime import datetime, timezone

import scrapy

from scrapy_news_crawler.items import ScrapyNewsCrawlerItem


class SinaTechSpider(scrapy.Spider):
    name = "sina_tech"
    allowed_domains = ["sina.com.cn", "sina.cn"]
    start_urls = ["https://tech.sina.com.cn/"]

    def parse(self, response):
        # #j_cardlist is the homepage feed; its first populated list is the
        # selected “热点” tab. Do not follow pagination or other tabs.
        seen = set()
        for rank, card in enumerate(
            response.css("#j_cardlist .cardlist-a__list")[1].css(".ty-card")[:20], 1
        ):
            anchor = card.css("h3.ty-card-tt a[href]")[:1]
            if not anchor:
                continue
            url = response.urljoin(anchor.attrib["href"].strip())
            if url in seen:
                continue
            seen.add(url)
            yield response.follow(
                url,
                callback=self.parse_article,
                cb_kwargs={"list_title": self.clean_text(anchor.xpath("string(.)").get()), "rank": rank},
            )
        self.logger.info("新浪科技热点列表前 20 条调度 %d 篇", len(seen))

    def parse_article(self, response, list_title, rank):
        body = response.css("#artibody")[:1] or response.css(".article")[:1]
        if not body:
            self.logger.warning("新浪正文容器不存在：%s", response.url)
            return
        paragraphs = body.xpath(".//p[not(ancestor::script) and not(ancestor::style)]")
        content = "\n".join(
            text for node in paragraphs
            if (text := self.clean_text(node.xpath(".//text()").getall()))
        )
        if not content:
            content = self.clean_text(body.xpath("string(.)").get())
        if not content:
            return

        images = []
        for src in body.css("img::attr(src), img::attr(data-src)").getall():
            image_url = response.urljoin(src.strip())
            if image_url.startswith(("http://", "https://")) and image_url not in images:
                images.append(image_url)
        published = (
            response.css('meta[property="article:published_time"]::attr(content)').get()
            or response.css('meta[property="bytedance:published_time"]::attr(content)').get()
            or response.css(".date::text").get()
        )
        yield ScrapyNewsCrawlerItem(
            url=response.url,
            title=self.clean_text(response.css("h1.main-title").xpath("string(.)").get()) or list_title,
            content=content,
            image_urls=images,
            source="新浪科技",
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
        except ValueError:
            for fmt in ("%Y年%m月%d日 %H:%M", "%Y-%m-%d %H:%M:%S"):
                try:
                    parsed = datetime.strptime(value.strip(), fmt).replace(tzinfo=timezone.utc)
                    return parsed.isoformat()
                except ValueError:
                    continue
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
