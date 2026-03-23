BOT_NAME = "amazon_scraper"

SPIDER_MODULES = ["amazon_scraper.spiders"]
NEWSPIDER_MODULE = "amazon_scraper.spiders"

ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS = 8
DOWNLOAD_DELAY = 1.5
RANDOMIZE_DOWNLOAD_DELAY = True
DOWNLOAD_TIMEOUT = 20


DOWNLOADER_MIDDLEWARES = {
    "amazon_scraper.middlewares.RotateUserAgentMiddleware": 400,
    "amazon_scraper.middlewares.ProxyMiddleware": 410,
    "amazon_scraper.middlewares.CloudflareFlaresolverrMiddleware": 420,
    "amazon_scraper.middlewares.DrissionPageMiddleware": 543,
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": 550,
}

SPIDER_MIDDLEWARES = {
    "amazon_scraper.middlewares.AmazonScraperSpiderMiddleware": 543,
}

RETRY_TIMES = 5
RETRY_HTTP_CODES = [403, 429, 500, 502, 503, 504]

DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

ITEM_PIPELINES = {
    "amazon_scraper.pipelines.AmazonScraperPipeline": 300,
}

USER_AGENTS=[
    'Mozilla/5.0 (Linux; Android 7.0; SM-A520F Build/NRD90M; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/65.0.3325.109 Mobile Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/67.0.3396.79 Safari/537.36',
]

PROXIES = [
            #"http://clps:clps@10.0.0.13:8511",
            "http://clps:clps@pavarottijin.3322.org:8511",
        ]
PROXY_TEST_URL="https://www.baidu.com/"
PROXY_BAN_SECONDS=600
PROXY_REQUEST_TIMEOUT=20

LOG_LEVEL = "INFO"

# Flaresolverr 服务地址（本地 docker 或服务）
FLARESOLVERR_URL = "http://localhost:8191/v1"

# DrissionPage 是否使用无头模式（True=后台不显示浏览器，False=显示浏览器窗口）
DRISSION_HEADLESS = True
DRISSION_GET_TIMEOUT = 20