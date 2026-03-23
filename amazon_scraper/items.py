import scrapy


class AmazonScraperItem(scrapy.Item):
    title = scrapy.Field()
    rating = scrapy.Field()
    review_nb = scrapy.Field()
    img = scrapy.Field()
    url = scrapy.Field()
    asin = scrapy.Field()
    prices_main = scrapy.Field()
    prices_per_unit = scrapy.Field()
    units = scrapy.Field()

