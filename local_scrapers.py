import logging
import time
import cloudscraper
from bs4 import BeautifulSoup
from urllib.parse import urljoin

logger = logging.getLogger(__name__)

def scrape_tokyo_dev(limit=50):
    """Scrape recent jobs from Tokyo-Dev."""
    scraper = cloudscraper.create_scraper()
    base_url = "https://www.tokyodev.com"
    jobs_url = f"{base_url}/jobs"
    
    logger.info(f"Fetching Tokyo-Dev job list from {jobs_url}")
    try:
        resp = scraper.get(jobs_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch Tokyo-Dev list: {e}")
        return []
        
    soup = BeautifulSoup(resp.text, 'html.parser')
    link_elements = soup.select('a[href*="/companies/"][href*="/jobs/"]')
    
    # Deduplicate links
    job_urls = list(dict.fromkeys(
        urljoin(base_url, a['href']) for a in link_elements
    ))
    
    if limit:
        job_urls = job_urls[:limit]
        
    logger.info(f"Found {len(job_urls)} jobs on Tokyo-Dev to scrape.")
    
    scraped_jobs = []
    for i, url in enumerate(job_urls):
        try:
            logger.info(f"Scraping Tokyo-Dev [{i+1}/{len(job_urls)}]: {url}")
            detail_resp = scraper.get(url, timeout=30)
            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
            
            title_el = detail_soup.find('h1')
            title = title_el.text.strip() if title_el else "Unknown Title"
            
            # Extract company from URL slug (e.g. /companies/company-name/jobs/...)
            try:
                company_slug = url.split('/companies/')[1].split('/')[0]
                company = company_slug.replace('-', ' ').title()
            except Exception:
                company = "Unknown Company"
                
            tags = [a.text.strip() for a in detail_soup.select('a[href*="/technologies/"]')]
            
            desc_el = detail_soup.select_one('article, main')
            description = desc_el.get_text(separator='\n', strip=True) if desc_el else "No description"
            
            scraped_jobs.append({
                "title": title,
                "company": company,
                "url": url,
                "tech_stack": tags,
                "full_description": description,
                "description": description[:500],
                "salary": "",
                "source": "tokyo_dev"
            })
            time.sleep(1) # Polite delay
        except Exception as e:
            logger.error(f"Error scraping Tokyo-Dev job {url}: {e}")
            
    return scraped_jobs


def scrape_japan_dev(limit=50):
    """Scrape recent jobs from Japan-Dev."""
    scraper = cloudscraper.create_scraper()
    base_url = "https://japan-dev.com"
    jobs_url = f"{base_url}/jobs"
    
    logger.info(f"Fetching Japan-Dev job list from {jobs_url}")
    try:
        resp = scraper.get(jobs_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch Japan-Dev list: {e}")
        return []
        
    soup = BeautifulSoup(resp.text, 'html.parser')
    link_elements = soup.select('a[href^="/jobs/"]')
    
    # Filter out non-job links and deduplicate
    job_urls = []
    for a in link_elements:
        href = a['href']
        # typical job link: /jobs/company-slug/job-slug
        if href.count('/') >= 3:
            full_url = urljoin(base_url, href)
            if full_url not in job_urls:
                job_urls.append(full_url)
                
    if limit:
        job_urls = job_urls[:limit]
        
    logger.info(f"Found {len(job_urls)} jobs on Japan-Dev to scrape.")
    
    scraped_jobs = []
    for i, url in enumerate(job_urls):
        try:
            logger.info(f"Scraping Japan-Dev [{i+1}/{len(job_urls)}]: {url}")
            detail_resp = scraper.get(url, timeout=30)
            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
            
            title_el = detail_soup.find('h1')
            title = title_el.text.strip() if title_el else "Unknown Title"
            
            try:
                company_slug = url.split('/jobs/')[1].split('/')[0]
                company = company_slug.replace('-', ' ').title()
            except Exception:
                company = "Unknown Company"
                
            tags = [a.text.strip() for a in detail_soup.select('a[href*="/technology"], a[href*="/tags"]')]
            
            desc_el = detail_soup.select_one('main, article, .job-details')
            description = desc_el.get_text(separator='\n', strip=True) if desc_el else "No description"
            
            scraped_jobs.append({
                "title": title,
                "company": company,
                "url": url,
                "tech_stack": tags,
                "full_description": description,
                "description": description[:500],
                "salary": "",
                "source": "japan_dev"
            })
            time.sleep(1) # Polite delay
        except Exception as e:
            logger.error(f"Error scraping Japan-Dev job {url}: {e}")
            
    return scraped_jobs


def scrape_gaijinpot(limit=50):
    """Scrape recent IT jobs from GaijinPot."""
    scraper = cloudscraper.create_scraper()
    base_url = "https://jobs.gaijinpot.com"
    jobs_url = f"{base_url}/job/index/category/17/lang/en"
    
    logger.info(f"Fetching GaijinPot job list from {jobs_url}")
    try:
        resp = scraper.get(jobs_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch GaijinPot list: {e}")
        return []
        
    soup = BeautifulSoup(resp.text, 'html.parser')
    link_elements = soup.select('a[href^="/en/job/"]')
    
    # Filter and deduplicate
    job_urls = []
    for a in link_elements:
        href = a.get('href', '')
        # Check if the href contains an ID (e.g., /en/job/123456)
        parts = href.split('/')
        if len(parts) >= 4 and parts[3].split('?')[0].isdigit():
            full_url = urljoin(base_url, href)
            if full_url not in job_urls:
                job_urls.append(full_url)
                
    if limit:
        job_urls = job_urls[:limit]
        
    logger.info(f"Found {len(job_urls)} jobs on GaijinPot to scrape.")
    
    scraped_jobs = []
    for i, url in enumerate(job_urls):
        try:
            logger.info(f"Scraping GaijinPot [{i+1}/{len(job_urls)}]: {url}")
            detail_resp = scraper.get(url, timeout=30)
            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
            
            title_el = detail_soup.find('h1')
            title = title_el.text.strip() if title_el else "Unknown Title"
            
            company_el = detail_soup.select_one('.company-name') or detail_soup.find('h2')
            company = company_el.text.strip() if company_el else "Unknown Company"
            
            # Gaijinpot doesn't have standard tech stack tags, so we leave it empty for LLM to extract
            tags = []
            
            desc_el = detail_soup.select_one('.job-description, .job-details, main, article')
            description = desc_el.get_text(separator='\n', strip=True) if desc_el else "No description"
            
            scraped_jobs.append({
                "title": title,
                "company": company,
                "url": url,
                "tech_stack": tags,
                "full_description": description,
                "description": description[:500],
                "salary": "",
                "source": "gaijinpot"
            })
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error scraping GaijinPot job {url}: {e}")
            
    return scraped_jobs


def scrape_careercross(limit=50):
    """Scrape recent IT jobs from CareerCross."""
    scraper = cloudscraper.create_scraper()
    base_url = "https://www.careercross.com"
    jobs_url = f"{base_url}/en/job-search/result?search%5Bjob_category_ids%5D%5B%5D=1"
    
    logger.info(f"Fetching CareerCross job list from {jobs_url}")
    try:
        resp = scraper.get(jobs_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch CareerCross list: {e}")
        return []
        
    soup = BeautifulSoup(resp.text, 'html.parser')
    link_elements = soup.select('a[href*="/en/job/"]')
    
    job_urls = []
    for a in link_elements:
        href = a.get('href', '')
        if 'viewed-user' in href:
            continue
        if any(char.isdigit() for char in href.split('/')[-1]):
            full_url = urljoin(base_url, href)
            if full_url not in job_urls:
                job_urls.append(full_url)
                
    if limit:
        job_urls = job_urls[:limit]
        
    logger.info(f"Found {len(job_urls)} jobs on CareerCross to scrape.")
    
    scraped_jobs = []
    for i, url in enumerate(job_urls):
        try:
            logger.info(f"Scraping CareerCross [{i+1}/{len(job_urls)}]: {url}")
            detail_resp = scraper.get(url, timeout=30)
            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
            
            title_el = detail_soup.find('h1')
            title = title_el.text.strip() if title_el else "Unknown Title"
            
            company_el = detail_soup.select_one('.company-name')
            company = company_el.text.strip() if company_el else "Unknown Company"
            
            tags = []
            
            desc_el = detail_soup.select_one('.job-details, .job-description, .panel-body, article, main')
            description = desc_el.get_text(separator='\n', strip=True) if desc_el else "No description"
            
            scraped_jobs.append({
                "title": title,
                "company": company,
                "url": url,
                "tech_stack": tags,
                "full_description": description,
                "description": description[:500],
                "salary": "",
                "source": "careercross"
            })
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error scraping CareerCross job {url}: {e}")
            
    return scraped_jobs


def scrape_green(limit=50):
    """Scrape recent IT jobs from Green."""
    scraper = cloudscraper.create_scraper()
    base_url = "https://www.green-japan.com"
    jobs_url = f"{base_url}/search_key"
    
    logger.info(f"Fetching Green job list from {jobs_url}")
    try:
        resp = scraper.get(jobs_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch Green list: {e}")
        return []
        
    soup = BeautifulSoup(resp.text, 'html.parser')
    link_elements = soup.select('a[href*="/job/"]')
    
    job_urls = []
    for a in link_elements:
        href = a.get('href', '')
        if '/job/' in href and any(char.isdigit() for char in href.split('/')[-1]):
            full_url = urljoin(base_url, href)
            if full_url not in job_urls:
                job_urls.append(full_url)
                
    if limit:
        job_urls = job_urls[:limit]
        
    logger.info(f"Found {len(job_urls)} jobs on Green to scrape.")
    
    scraped_jobs = []
    for i, url in enumerate(job_urls):
        try:
            logger.info(f"Scraping Green [{i+1}/{len(job_urls)}]: {url}")
            detail_resp = scraper.get(url, timeout=30)
            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
            
            title_el = detail_soup.select_one('.job-title') or detail_soup.find('h2')
            title = title_el.text.strip() if title_el else "Unknown Title"
            
            company_el = detail_soup.select_one('.company-name') or detail_soup.find('h1')
            company = company_el.text.strip() if company_el else "Unknown Company"
            
            tags = [a.text.strip() for a in detail_soup.select('a[href*="/skill/"]')]
            
            desc_el = detail_soup.select_one('.job-detail, .job-offer-detail, main, article')
            description = desc_el.get_text(separator='\n', strip=True) if desc_el else "No description"
            
            scraped_jobs.append({
                "title": title,
                "company": company,
                "url": url,
                "tech_stack": tags,
                "full_description": description,
                "description": description[:500],
                "salary": "",
                "source": "green"
            })
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error scraping Green job {url}: {e}")
            
    return scraped_jobs


def scrape_daijob(limit=50):
    """Scrape recent jobs from Daijob."""
    scraper = cloudscraper.create_scraper()
    base_url = "https://www.daijob.com"
    # Added kw=engineer to filter strictly for tech/engineering roles
    jobs_url = f"{base_url}/en/jobs/search_result?target=category&num_pages=1&kw=engineer"
    
    logger.info(f"Fetching Daijob job list from {jobs_url}")
    try:
        resp = scraper.get(jobs_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch Daijob list: {e}")
        return []
        
    soup = BeautifulSoup(resp.text, 'html.parser')
    link_elements = soup.select('a')
    
    job_urls = []
    for a in link_elements:
        href = a.get('href', '')
        if '/en/jobs/detail/' in href:
            full_url = urljoin(base_url, href)
            if full_url not in job_urls:
                job_urls.append(full_url)
                
    if limit:
        job_urls = job_urls[:limit]
        
    logger.info(f"Found {len(job_urls)} jobs on Daijob to scrape.")
    
    scraped_jobs = []
    for i, url in enumerate(job_urls):
        try:
            logger.info(f"Scraping Daijob [{i+1}/{len(job_urls)}]: {url}")
            detail_resp = scraper.get(url, timeout=30)
            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
            
            title_el = detail_soup.find('h1') or detail_soup.select_one('.job_title')
            title = title_el.text.strip() if title_el else "Unknown Title"
            
            company_el = detail_soup.select_one('.company_name') or detail_soup.find('h2')
            company = company_el.text.strip() if company_el else "Unknown Company"
            
            tags = []
            
            desc_el = detail_soup.select_one('.job_detail_box, main, article, body')
            description = desc_el.get_text(separator='\n', strip=True) if desc_el else "No description"
            
            scraped_jobs.append({
                "title": title,
                "company": company,
                "url": url,
                "tech_stack": tags,
                "full_description": description,
                "description": description[:500],
                "salary": "",
                "source": "daijob"
            })
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error scraping Daijob job {url}: {e}")
            
    return scraped_jobs


def scrape_wantedly(limit=50):
    """Scrape recent projects/jobs from Wantedly."""
    scraper = cloudscraper.create_scraper()
    base_url = "https://www.wantedly.com"
    # occupations[]=1 specifically filters for IT/Web Engineering
    jobs_url = f"{base_url}/projects?type=mixed&page=1&occupations%5B%5D=1"
    
    logger.info(f"Fetching Wantedly job list from {jobs_url}")
    try:
        resp = scraper.get(jobs_url, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to fetch Wantedly list: {e}")
        return []
        
    soup = BeautifulSoup(resp.text, 'html.parser')
    link_elements = soup.select('a')
    
    job_urls = []
    for a in link_elements:
        href = a.get('href', '')
        if '/projects/' in href and any(char.isdigit() for char in href.split('/')[-1].split('?')[0]):
            full_url = urljoin(base_url, href)
            if full_url not in job_urls:
                job_urls.append(full_url)
                
    if limit:
        job_urls = job_urls[:limit]
        
    logger.info(f"Found {len(job_urls)} jobs on Wantedly to scrape.")
    
    scraped_jobs = []
    for i, url in enumerate(job_urls):
        try:
            logger.info(f"Scraping Wantedly [{i+1}/{len(job_urls)}]: {url}")
            detail_resp = scraper.get(url, timeout=30)
            detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
            
            title_el = detail_soup.find('h1')
            title = title_el.text.strip() if title_el else "Unknown Title"
            
            company_el = detail_soup.select_one('.company-name') or detail_soup.select_one('a[href^="/companies/"]')
            company = company_el.text.strip() if company_el else "Unknown Company"
            
            tags = [a.text.strip() for a in detail_soup.select('a[href*="/projects?skills"]')]
            
            desc_el = detail_soup.select_one('.project-detail, article, main, body')
            description = desc_el.get_text(separator='\n', strip=True) if desc_el else "No description"
            
            scraped_jobs.append({
                "title": title,
                "company": company,
                "url": url,
                "tech_stack": tags,
                "full_description": description,
                "description": description[:500],
                "salary": "",
                "source": "wantedly"
            })
            time.sleep(1)
        except Exception as e:
            logger.error(f"Error scraping Wantedly job {url}: {e}")
            
    return scraped_jobs
