import json
from local_scrapers import scrape_japan_dev, scrape_tokyo_dev

def main():
    print("Starting scrapers...")
    
    # Scrape jobs (you can adjust the limit if needed)
    print("Scraping Tokyo-Dev...")
    tokyodev_jobs = scrape_tokyo_dev(limit=10)
    
    print("Scraping Japan-Dev...")
    japandev_jobs = scrape_japan_dev(limit=10)
    
    # Combine results
    all_jobs = tokyodev_jobs + japandev_jobs
    print(f"Successfully scraped {len(all_jobs)} jobs in total.")
    
    # Save to JSON file
    output_filename = "scraped_jobs.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(all_jobs, f, indent=2, ensure_ascii=False)
        
    print(f"Data has been saved to {output_filename}")

if __name__ == "__main__":
    main()
