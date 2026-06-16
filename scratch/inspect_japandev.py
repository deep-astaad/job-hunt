import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper()
jd = scraper.get("https://japan-dev.com/jobs")
soup = BeautifulSoup(jd.text, 'html.parser')
links = soup.select('a[href^="/jobs/"]')
print("Japan-Dev job links:", len(links))
if links:
    print("Sample:", links[0]['href'])
    
# Let's also check if it's rendered at all in the HTML or if we need to query Algolia API
