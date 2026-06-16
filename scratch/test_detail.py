import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper()

def test_td_detail():
    url = "https://www.tokyodev.com/jobs/paytner-software-engineer"
    resp = scraper.get(url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    title = soup.find('h1')
    title_text = title.text.strip() if title else 'No title'
    
    # company might be in a header or h2
    company_text = "Unknown"
    # tags might be in ul or a with /technologies/
    tags = [a.text.strip() for a in soup.select('a[href*="/technologies/"]')]
    
    desc_node = soup.select_one('article, main')
    desc_text = desc_node.text.strip()[:100] if desc_node else "No desc"
    
    print("Tokyo-Dev:")
    print(" Title:", title_text)
    print(" Tags:", tags)
    print(" Desc:", desc_text)

def test_jd_detail():
    url = "https://japan-dev.com/jobs/paypay-securities/paypay-securities-backend-engineer-ljuyvo"
    resp = scraper.get(url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    title = soup.find('h1')
    title_text = title.text.strip() if title else 'No title'
    
    tags = [a.text.strip() for a in soup.select('a[href*="/technology"], a[href*="/tags"]')]
    
    desc_node = soup.select_one('main, article, .job-details')
    desc_text = desc_node.text.strip()[:100] if desc_node else "No desc"
    
    print("\nJapan-Dev:")
    print(" Title:", title_text)
    print(" Tags:", tags)
    print(" Desc:", desc_text)

test_td_detail()
test_jd_detail()
