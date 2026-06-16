import cloudscraper
from bs4 import BeautifulSoup
import json

scraper = cloudscraper.create_scraper()

def test_gaijinpot():
    print("--- GaijinPot ---")
    url = "https://jobs.gaijinpot.com/index/index/lang/en"
    resp = scraper.get(url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.select('a')
    job_links = [a['href'] for a in links if 'href' in a.attrs and '/job/view/job_id/' in a['href']]
    print("Found job links:", len(job_links))
    if job_links:
        print("Sample:", job_links[0])

def test_findy():
    print("--- Findy Global ---")
    url = "https://global.findy-code.io/jobs"
    resp = scraper.get(url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    next_data = soup.find('script', id='__NEXT_DATA__')
    if next_data:
        data = json.loads(next_data.string)
        print("Found NEXT_DATA. keys:", data.keys())
        try:
            jobs = data['props']['pageProps']['initialState']['jobs']['jobList']
            print("Findy jobs in state:", len(jobs))
        except Exception as e:
            print("Could not find jobs in next data:", e)

test_gaijinpot()
test_findy()
