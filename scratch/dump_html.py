import cloudscraper
scraper = cloudscraper.create_scraper()

with open("scratch/gaijinpot.html", "w") as f:
    f.write(scraper.get("https://jobs.gaijinpot.com/job/index/category/17/lang/en").text)

with open("scratch/findy.html", "w") as f:
    f.write(scraper.get("https://global.findy-code.io/jobs").text)
