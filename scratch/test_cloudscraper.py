import cloudscraper
from bs4 import BeautifulSoup

def test_sites():
    scraper = cloudscraper.create_scraper()
    
    jd = scraper.get("https://japan-dev.com/jobs")
    print("Japan-Dev:", jd.status_code)
    jd_soup = BeautifulSoup(jd.text, 'html.parser')
    jd_next = jd_soup.find('script', id='__NEXT_DATA__')
    if jd_next:
        print("Found NEXT_DATA in Japan-Dev")
    else:
        print("No NEXT_DATA in Japan-Dev. Title:", jd_soup.title.string if jd_soup.title else 'None')
        
    td = scraper.get("https://www.tokyodev.com/jobs")
    print("Tokyo-Dev:", td.status_code)
    td_soup = BeautifulSoup(td.text, 'html.parser')
    links = td_soup.select('a[href*="/companies/"][href*="/jobs/"]')
    print("Tokyo-Dev links:", len(links))

test_sites()
