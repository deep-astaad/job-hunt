import cloudscraper
from bs4 import BeautifulSoup
scraper = cloudscraper.create_scraper()

d = scraper.get("https://jobs.gaijinpot.com/en/job/158883")
ds = BeautifulSoup(d.text, 'html.parser')
h1 = ds.find('h1')
h2 = ds.find('h2')
print("GP H1:", h1.text.strip() if h1 else 'none')
print("GP H2:", h2.text.strip() if h2 else 'none')
# find anything with class company
c = ds.select_one('[class*="company"]')
print("GP Company Class:", c.text.strip() if c else 'none')

d2 = scraper.get("https://www.green-japan.com/company/11162/job/320420")
ds2 = BeautifulSoup(d2.text, 'html.parser')
h1_2 = ds2.find('h1')
h2_2 = ds2.find('h2')
print("GR H1:", h1_2.text.strip() if h1_2 else 'none')
print("GR H2:", h2_2.text.strip() if h2_2 else 'none')
