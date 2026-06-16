import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper()

def test_daijob_detail():
    print("--- Daijob Detail ---")
    url = "https://www.daijob.com/en/jobs/detail/1493431"
    try:
        resp = scraper.get(url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.find('h1')
        company = soup.select_one('.company_name') or soup.find('h2')
        print("Title:", title.text.strip() if title else 'None')
        print("Company:", company.text.strip() if company else 'None')
    except Exception as e:
        print("Error:", e)

def test_wantedly_detail():
    print("--- Wantedly Detail ---")
    url = "https://www.wantedly.com/projects/2345969"
    try:
        resp = scraper.get(url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.find('h1')
        # Wantedly usually has the company name in a profile link or header
        company = soup.select_one('.company-name') or soup.select_one('a[href^="/companies/"]')
        print("Title:", title.text.strip() if title else 'None')
        print("Company:", company.text.strip() if company else 'None')
    except Exception as e:
        print("Error:", e)

test_daijob_detail()
test_wantedly_detail()
