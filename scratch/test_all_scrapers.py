import json
from local_scrapers import (
    scrape_japan_dev,
    scrape_tokyo_dev,
    scrape_gaijinpot,
    scrape_careercross,
    scrape_green
)

def test_all():
    print("Testing GaijinPot...")
    g = scrape_gaijinpot(limit=2)
    print(f"GaijinPot jobs: {len(g)}")
    if g:
        print("Sample:", g[0].get('title'), "|", g[0].get('company'))
        
    print("\nTesting CareerCross...")
    cc = scrape_careercross(limit=2)
    print(f"CareerCross jobs: {len(cc)}")
    if cc:
        print("Sample:", cc[0].get('title'), "|", cc[0].get('company'))
        
    print("\nTesting Green...")
    gr = scrape_green(limit=2)
    print(f"Green jobs: {len(gr)}")
    if gr:
        print("Sample:", gr[0].get('title'), "|", gr[0].get('company'))

    print("\nTesting Japan-Dev...")
    jd = scrape_japan_dev(limit=1)
    print(f"Japan-Dev jobs: {len(jd)}")
    
    print("\nTesting Tokyo-Dev...")
    td = scrape_tokyo_dev(limit=1)
    print(f"Tokyo-Dev jobs: {len(td)}")

if __name__ == "__main__":
    test_all()
