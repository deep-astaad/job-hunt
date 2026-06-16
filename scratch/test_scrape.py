import requests
from bs4 import BeautifulSoup
import json

def test_japan_dev():
    url = "https://japan-dev.com/jobs"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)
    print("Japan-Dev status:", resp.status_code)
    # Check if we can find __NEXT_DATA__ or similar
    soup = BeautifulSoup(resp.text, 'html.parser')
    next_data = soup.find('script', id='__NEXT_DATA__')
    if next_data:
        print("Japan-Dev has __NEXT_DATA__")
    else:
        print("Japan-Dev has no __NEXT_DATA__")

def test_tokyo_dev():
    url = "https://www.tokyodev.com/jobs"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers)
    print("Tokyo-Dev status:", resp.status_code)
    # Look for jobs in HTML
    soup = BeautifulSoup(resp.text, 'html.parser')
    jobs = soup.select('li.job-list-item, article, a[href*="/jobs/"]')
    print(f"Tokyo-Dev found {len(jobs)} potential job links")

test_japan_dev()
test_tokyo_dev()
