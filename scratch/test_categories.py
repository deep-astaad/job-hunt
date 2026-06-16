import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper()

def test_daijob_it():
    print("--- Daijob IT ---")
    # Trying common category parameters or just a keyword
    url = "https://www.daijob.com/en/jobs/search_result?target=category&kw=engineer&job_category[]=1"
    resp = scraper.get(url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.select('a')
    job_links = [a['href'] for a in links if 'href' in a.attrs and '/en/jobs/detail/' in a['href']]
    print("Found links with kw=engineer & category 1:", len(set(job_links)))

    url2 = "https://www.daijob.com/en/jobs/search_result?target=category&keyword=engineer"
    resp2 = scraper.get(url2)
    soup2 = BeautifulSoup(resp2.text, 'html.parser')
    job_links2 = [a['href'] for a in soup2.select('a') if 'href' in a.attrs and '/en/jobs/detail/' in a['href']]
    print("Found links with keyword=engineer:", len(set(job_links2)))

    # Another daijob URL structure:
    url3 = "https://www.daijob.com/en/jobs/search_result?job_category[]=21" # 21 is often IT in some systems. Let's check 1, 2, 3
    for i in [1, 10, 21]:
        resp3 = scraper.get(f"https://www.daijob.com/en/jobs/search_result?job_category[]={i}")
        soup3 = BeautifulSoup(resp3.text, 'html.parser')
        job_links3 = [a['href'] for a in soup3.select('a') if 'href' in a.attrs and '/en/jobs/detail/' in a['href']]
        print(f"Found links with job_category[]={i}:", len(set(job_links3)))


def test_wantedly_it():
    print("--- Wantedly IT ---")
    # 1 is Engineer in Wantedly
    url = "https://www.wantedly.com/projects?type=mixed&page=1&occupations%5B%5D=1"
    resp = scraper.get(url)
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.select('a')
    job_links = [a['href'] for a in links if 'href' in a.attrs and '/projects/' in a['href']]
    job_links = [l for l in job_links if any(char.isdigit() for char in l.split('/')[-1])]
    print("Found Wantedly engineer links:", len(set(job_links)))

test_daijob_it()
test_wantedly_it()
