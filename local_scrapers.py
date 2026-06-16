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
                "source": "tokyodev"
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
                "source": "japan-dev"
            })
            time.sleep(1) # Polite delay
        except Exception as e:
            logger.error(f"Error scraping Japan-Dev job {url}: {e}")
            
    return scraped_jobs
