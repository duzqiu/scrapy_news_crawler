# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class ScrapyNewsCrawlerItem(scrapy.Item):
    """新闻文章数据结构。"""

    # 文章原始链接，建议作为 PostgreSQL 的唯一键。
    url = scrapy.Field()

    # 新闻标题。
    title = scrapy.Field()

    # 清洗后的正文内容。
    content = scrapy.Field()

    # 图片链接列表，例如：["https://example.com/a.jpg"]。
    image_urls = scrapy.Field()

    # 新闻渠道或来源，例如：BBC、新华网、某新闻频道。
    source = scrapy.Field()

    # 原始发布时间；建议 Spider 中统一转换为 datetime。
    published_at = scrapy.Field()

    # 抓取时间，由 Spider 或 Pipeline 写入。
    crawled_at = scrapy.Field()

    # 可选：热点榜单名称，例如“实时热榜”“24小时热门”。
    board = scrapy.Field()

    # 可选：文章在热点榜单中的排名。
    rank = scrapy.Field()
