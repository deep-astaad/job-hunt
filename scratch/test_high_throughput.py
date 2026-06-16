import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper()

def test_daijob():
    print("--- Daijob ---")
    url = "https://www.daijob.com/en/jobs/search_result?target=category&num_pages=1"
    try:
        resp = scraper.get(url)
        print("Status:", resp.status_code)
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select('a')
        job_links = [a['href'] for a in links if 'href' in a.attrs and '/en/jobs/detail/' in a['href']]
        # Deduplicate
        job_links = list(set(job_links))
        print("Found job links:", len(job_links))
        if job_links:
            print("Sample link:", job_links[0])
    except Exception as e:
        print("Error:", e)

def test_wantedly():
    print("--- Wantedly ---")
    url = "https://www.wantedly.com/projects"
    try:
        # Sometimes wantedly blocks cloudscraper, let's see
        resp = scraper.get(url)
        print("Status:", resp.status_code)
        soup = BeautifulSoup(resp.text, 'html.parser')
        links = soup.select('a')
        job_links = [a['href'] for a in links if 'href' in a.attrs and '/projects/' in a['href']]
        job_links = [l for l in job_links if any(char.isdigit() for char in l.split('/')[-1])]
        job_links = list(set(job_links))
        print("Found job links:", len(job_links))
        if job_links:
            print("Sample link:", job_links[0])
    except Exception as e:
        print("Error:", e)

test_daijob()
test_wantedly()
