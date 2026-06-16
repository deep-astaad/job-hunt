import requests
from bs4 import BeautifulSoup

def test_japan_dev():
    url = "https://japan-dev.com/jobs"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(resp.text, 'html.parser')
    next_data = soup.find('script', id='__NEXT_DATA__')
    if next_data:
        import json
        data = json.loads(next_data.string)
        print("Japan-Dev jobs keys:", data.keys())
        # Let's dig into the props
        try:
            props = data['props']['pageProps']
            print("Japan-Dev props keys:", props.keys())
            if 'initialState' in props:
                print("initialState keys:", props['initialState'].keys())
        except Exception as e:
            print("Error parsing Japan-Dev props:", e)
    else:
        print("No NEXT_DATA found for Japan-Dev")

def test_tokyo_dev():
    url = "https://www.tokyodev.com/jobs"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(resp.text, 'html.parser')
    links = soup.select('a[href*="/companies/"][href*="/jobs/"]')
    print("Tokyo-Dev links found:", len(links))
    if links:
        print("Sample link:", links[0]['href'])

test_japan_dev()
test_tokyo_dev()
