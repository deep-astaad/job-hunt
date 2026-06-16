import cloudscraper
from bs4 import BeautifulSoup
import json
scraper = cloudscraper.create_scraper()

def test_careercross():
    print("--- CareerCross ---")
    url = "https://www.careercross.com/en/job-search/result?search%5Bkeyword%5D=&search%5Bjob_category_ids%5D%5B%5D=1"
    try:
        resp = scraper.get(url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select('a[href*="/en/job/"]')
        job_links = [a['href'] for a in links if '/en/job/' in a['href'] and 'viewed-user' not in a['href']]
        # Filter numeric job links
        job_links = [l for l in job_links if any(char.isdigit() for char in l.split('/')[-1])]
        if not job_links:
            print("No links found")
            return
        detail_url = "https://www.careercross.com" + job_links[0] if not job_links[0].startswith("http") else job_links[0]
        print("Detail URL:", detail_url)
        d = scraper.get(detail_url)
        ds = BeautifulSoup(d.text, 'html.parser')
        title = ds.select_one('h1')
        company = ds.select_one('.company-name') or ds.select_one('h2')
        print("Title:", title.text.strip() if title else 'None')
        print("Company:", company.text.strip() if company else 'None')
    except Exception as e:
        print("CareerCross Error:", e)

def test_green():
    print("--- Green ---")
    url = "https://www.green-japan.com/search_key"
    try:
        resp = scraper.get(url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select('a[href*="/job/"]')
        job_links = [a['href'] for a in links if '/job/' in a['href']]
        if not job_links:
            print("No links found")
            return
        detail_url = "https://www.green-japan.com" + job_links[0] if not job_links[0].startswith("http") else job_links[0]
        print("Detail URL:", detail_url)
        d = scraper.get(detail_url)
        ds = BeautifulSoup(d.text, 'html.parser')
        title = ds.select_one('h2') or ds.select_one('.job-title')
        company = ds.select_one('.company-name') or ds.select_one('h1')
        print("Title:", title.text.strip() if title else 'None')
        print("Company:", company.text.strip() if company else 'None')
    except Exception as e:
        print("Green Error:", e)

def test_gaijinpot():
    print("--- GaijinPot ---")
    url = "https://jobs.gaijinpot.com/job/index/category/17/lang/en"
    try:
        resp = scraper.get(url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select('a')
        job_links = [a['href'] for a in links if 'href' in a.attrs and '/job/view/job_id/' in a['href']]
        if not job_links:
            print("No links found")
            return
        detail_url = job_links[0]
        print("Detail URL:", detail_url)
        d = scraper.get(detail_url)
        ds = BeautifulSoup(d.text, 'html.parser')
        title = ds.select_one('h1')
        company = ds.select_one('.company-name') or ds.select_one('h2')
        print("Title:", title.text.strip() if title else 'None')
        print("Company:", company.text.strip() if company else 'None')
    except Exception as e:
        print("GaijinPot Error:", e)

def test_findy():
    print("--- Findy Global ---")
    url = "https://global.findy-code.io/jobs"
    try:
        resp = scraper.get(url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        next_data = soup.find('script', id='__NEXT_DATA__')
        if next_data:
            data = json.loads(next_data.string)
            try:
                jobs = data['props']['pageProps']['initialState']['jobs']['jobList']
                print("Found jobs in NEXT_DATA:", len(jobs))
                if jobs:
                    j = jobs[0]
                    print("Title:", j.get('title'))
                    print("Company:", j.get('companyName'))
                return
            except Exception as e:
                pass
        
        # Alternatively, findy might have an API or direct DOM nodes
        links = soup.select('a[href*="/job-postings/"]')
        job_links = [a['href'] for a in links if '/job-postings/' in a['href']]
        if not job_links:
            print("No links found")
            return
        detail_url = "https://global.findy-code.io" + job_links[0] if not job_links[0].startswith("http") else job_links[0]
        print("Detail URL:", detail_url)
        d = scraper.get(detail_url)
        ds = BeautifulSoup(d.text, 'html.parser')
        title = ds.select_one('h1')
        print("Title:", title.text.strip() if title else 'None')
    except Exception as e:
        print("Findy Error:", e)

test_careercross()
test_green()
test_gaijinpot()
test_findy()
