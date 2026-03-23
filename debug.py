from scrapy.cmdline import execute

execute(["scrapy", "crawl", "AmazonSpider", "-a", "keyword=mouse", "-a", "min_products=50"])
