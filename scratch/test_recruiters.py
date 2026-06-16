import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper()

def test_robert_walters():
    print("--- Robert Walters ---")
    url = "https://www.robertwalters.co.jp/en/it/jobs.html"
    try:
        resp = scraper.get(url, timeout=10)
        print("Status:", resp.status_code)
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select('a[href*="/job/"]')
        print("Found job links:", len(links))
        if links:
            print("Sample link:", links[0].get('href'))
    except Exception as e:
        print("Error:", e)

def test_hays():
    print("--- Hays ---")
    url = "https://www.hays.co.jp/en/job-search/information-technology-jobs"
    try:
        resp = scraper.get(url, timeout=10)
        print("Status:", resp.status_code)
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select('a')
        job_links = [a.get('href') for a in links if a.get('href') and '/job/' in a.get('href')]
        print("Found job links:", len(job_links))
        if job_links:
            print("Sample link:", job_links[0])
    except Exception as e:
        print("Error:", e)

test_robert_walters()
test_hays()
