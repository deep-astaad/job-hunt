# my_actor/main.py
import asyncio
from crawlee.crawlers import PlaywrightCrawler
from crawlee import Request

# FIX: Removed the '.' before routes
from routes import router

async def main() -> None:
    crawler = PlaywrightCrawler(
        request_handler=router,
        # max_concurrency=5,
        # max_requests_per_crawl=50, 
        headless=True,
    )

    await crawler.add_requests([
        Request.from_url('https://japan-dev.com/jobs-in-japan-for-english-speakers', label='JAPAN_DEV_LIST'),
        Request.from_url('https://www.tokyodev.com/jobs?query%5B%5D=&japanese_requirement%5B%5D=none&salary=', label='TOKYO_DEV_LIST')
    ])

    print('Starting the crawl...')
    await crawler.run()
    print('Crawl finished. Check the storage/datasets/default/ directory for results!')

if __name__ == '__main__':
    asyncio.run(main())