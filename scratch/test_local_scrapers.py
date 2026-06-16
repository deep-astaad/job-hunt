from local_scrapers import scrape_japan_dev, scrape_tokyo_dev
import json

jd = scrape_japan_dev(limit=2)
print("Japan-Dev jobs:", len(jd))
if jd:
    print(json.dumps(jd[0], indent=2))

td = scrape_tokyo_dev(limit=2)
print("Tokyo-Dev jobs:", len(td))
if td:
    print(json.dumps(td[0], indent=2))
