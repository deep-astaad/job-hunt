import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper()

def test_gaijinpot():
    print("--- GaijinPot ---")
    url = "https://jobs.gaijinpot.com/job/index/lang/en?category=17" # IT category
    resp = scraper.get(url)
    print("Status:", resp.status_code)
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.select('a[href*="/job/view/"]')
    print("Found links:", len(links))
    if links: print("Sample:", links[0]['href'])

def test_careercross():
    print("--- CareerCross ---")
    url = "https://www.careercross.com/en/job-search/result?search%5Bkeyword%5D=&search%5Bjob_category_ids%5D%5B%5D=1" # IT category
    resp = scraper.get(url)
    print("Status:", resp.status_code)
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.select('a[href*="/en/job/"]')
    print("Found links:", len(links))
    if links: print("Sample:", links[0]['href'])

def test_green():
    print("--- Green ---")
    url = "https://www.green-japan.com/search_key"
    resp = scraper.get(url)
    print("Status:", resp.status_code)
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.select('a[href*="/job/"]')
    print("Found links:", len(links))
    if links: print("Sample:", links[0]['href'])

def test_findy():
    print("--- Findy Global ---")
    url = "https://global.findy-code.io/jobs"
    resp = scraper.get(url)
    print("Status:", resp.status_code)
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.select('a[href*="/jobs/"]')
    print("Found links:", len(links))
    if links: print("Sample:", links[0]['href'])

test_gaijinpot()
test_careercross()
test_green()
test_findy()
