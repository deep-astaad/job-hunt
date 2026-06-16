import json
from local_scrapers import scrape_daijob, scrape_wantedly

def test_high_throughput():
    print("Testing Daijob...")
    d = scrape_daijob(limit=2)
    print(f"Daijob jobs: {len(d)}")
    if d:
        print("Sample:", d[0].get('title'), "|", d[0].get('company'))
        
    print("\nTesting Wantedly...")
    w = scrape_wantedly(limit=2)
    print(f"Wantedly jobs: {len(w)}")
    if w:
        print("Sample:", w[0].get('title'), "|", w[0].get('company'))

if __name__ == "__main__":
    test_high_throughput()
