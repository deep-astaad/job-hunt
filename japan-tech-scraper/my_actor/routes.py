# my_actor/routes.py
from crawlee.crawlers import PlaywrightCrawlingContext
from crawlee.router import Router

router = Router[PlaywrightCrawlingContext]()

# --- JAPAN-DEV ROUTES ---
@router.handler('JAPAN_DEV_LIST')
async def japan_dev_list(context: PlaywrightCrawlingContext) -> None:
    context.log.info(f"Enqueuing Japan-Dev jobs from: {context.request.url}")
    page = context.page
    
    # Wait for the first batch of Algolia results to render
    await page.wait_for_timeout(2000)

    page_num = 1
    while True:
        context.log.info(f"Scraping Japan-Dev page {page_num}...")
        
        # 1. Enqueue all job links currently visible on the DOM
        # Crawlee automatically ignores duplicates, so it's perfectly safe 
        # to scoop up everything on the screen over and over.
        await context.enqueue_links(
            selector='a[href*="/jobs/"]',
            label='JAPAN_DEV_DETAIL'
        )

        # 2. Look for the Algolia Next Page button
        # We ensure the <li> does NOT have the "--disabled" class (which Algolia adds on the last page)
        next_button = page.locator('li.ais-Pagination-item--nextPage:not(.ais-Pagination-item--disabled) a').first
        
        if await next_button.is_visible():
            # Click it and wait for the React frontend to fetch the next batch
            await next_button.click()
            await page.wait_for_timeout(2000) 
            page_num += 1
        else:
            context.log.info("No more next pages. Reached the end of Japan-Dev!")
            break

@router.handler('JAPAN_DEV_DETAIL')
async def japan_dev_detail(context: PlaywrightCrawlingContext) -> None:
    context.log.info(f"Scraping Japan-Dev job: {context.request.url}")
    page = context.page
    await page.wait_for_selector('h1')
    
    try:
        title = await page.locator('h1').first.inner_text()
    except Exception:
        title = 'No title found'

    try:
        company_slug = context.request.url.split('/jobs/')[1].split('/')[0]
        company = company_slug.replace('-', ' ').title()
    except Exception:
        company = 'Unknown Company'

    try:
        tags = await page.locator('a[href*="/technology"], a[href*="/tags"]').all_inner_texts()
        tech_stack = list(set([tag.strip() for tag in tags if tag.strip()]))
    except Exception:
        tech_stack = []

    try:
        description = await page.locator('main, article, .job-details').first.inner_text()
    except Exception:
        description = 'No description found'
        
    await context.push_data({
        'source': 'Japan-Dev',
        'url': context.request.url,
        'company': company,
        'title': title,
        'tech_stack': tech_stack,
        'full_description': description,
    })

# --- TOKYODEV ROUTES ---
@router.handler('TOKYO_DEV_LIST')
async def tokyo_dev_list(context: PlaywrightCrawlingContext) -> None:
    context.log.info(f"Enqueuing TokyoDev jobs from: {context.request.url}")
    
    # FIX: Updated selector to only match actual job detail URLs
    # which contain both "/companies/" and "/jobs/"
    await context.enqueue_links(
        selector='a[href*="/companies/"][href*="/jobs/"]',
        label='TOKYO_DEV_DETAIL',
        base_url='https://www.tokyodev.com'
    )

@router.handler('TOKYO_DEV_DETAIL')
async def tokyo_dev_detail(context: PlaywrightCrawlingContext) -> None:
    context.log.info(f"Scraping TokyoDev job: {context.request.url}")
    page = context.page
    await page.wait_for_selector('h1')
    
    # 1. Title
    try:
        title = await page.locator('h1').first.inner_text()
    except Exception:
        title = 'No title found'

    # 2. Company
    try:
        # FIX: Safely extract the company directly from the URL slug
        # e.g., /companies/money-forward/jobs/... -> Money Forward
        company_slug = context.request.url.split('/companies/')[1].split('/')[0]
        company = company_slug.replace('-', ' ').title()
    except Exception:
        company = 'Unknown Company'

    # 3. Tech Stack Tags
    try:
        tags = await page.locator('a[href*="/technologies/"]').all_inner_texts()
        tech_stack = list(set([tag.strip() for tag in tags if tag.strip()]))
    except Exception:
        tech_stack = []

    # 4. Full Job Description
    try:
        # TokyoDev usually wraps the JD in an article tag or a div next to the apply button
        description = await page.locator('article, main').first.inner_text()
    except Exception:
        description = 'No description found'
        
    await context.push_data({
        'source': 'TokyoDev',
        'url': context.request.url,
        'company': company,
        'title': title,
        'tech_stack': tech_stack,
        'full_description': description,
    })