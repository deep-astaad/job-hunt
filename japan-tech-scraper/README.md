## Python Crawlee with Playwright template

<!-- This is an Apify template readme -->

A template for [web scraping](https://apify.com/web-scraping) data from websites starting from provided URLs using Python. The starting URLs are passed through the Actor's input schema, defined by the [input schema](https://docs.apify.com/platform/actors/development/input-schema). The template uses [Crawlee for Python](https://crawlee.dev/python) for efficient web crawling, making requests via headless browser managed by [Playwright](https://playwright.dev/python/), and handling each request through a user-defined handler that uses [Playwright](https://playwright.dev/python/) API to extract data from the page. Enqueued URLs are managed in the [request queue](https://crawlee.dev/python/api/class/RequestQueue), and the extracted data is saved in a [dataset](https://crawlee.dev/python/api/class/Dataset) for easy access.

## Included features

- **[Apify SDK](https://docs.apify.com/sdk/python/)** - a toolkit for building Apify [Actors](https://apify.com/actors) in Python.
- **[Crawlee for Python](https://crawlee.dev/python/)** - a web scraping and browser automation library.
- **[Input schema](https://docs.apify.com/platform/actors/development/input-schema)** - define and validate a schema for your Actor's input.
- **[Request queue](https://crawlee.dev/python/api/class/RequestQueue)** - manage the URLs you want to scrape in a queue.
- **[Dataset](https://crawlee.dev/python/api/class/Dataset)** - store and access structured data extracted from web pages.
- **[Playwright](https://playwright.dev/python/)** - a library for managing headless browsers.

## Resources

- [Video introduction to Python SDK](https://www.youtube.com/watch?v=C8DmvJQS3jk)
- [Webinar introducing to Crawlee for Python](https://www.youtube.com/live/ip8Ii0eLfRY)
- [Apify Python SDK documentation](https://docs.apify.com/sdk/python/)
- [Crawlee for Python documentation](https://crawlee.dev/python/docs/quick-start)
- [Python tutorials in Academy](https://docs.apify.com/academy/python)
- [Integration with Make, GitHub, Zapier, Google Drive, and other apps](https://apify.com/integrations)
- [Video guide on getting scraped data using Apify API](https://www.youtube.com/watch?v=ViYYDHSBAKM)
- A short guide on how to build web scrapers using code templates:

[web scraper template](https://www.youtube.com/watch?v=u-i-Korzf8w)


## Getting started

For complete information [see this article](https://docs.apify.com/platform/actors/development#build-actor-locally). To run the Actor use the following command:

```bash
apify run
```

## Deploy to Apify

### Connect Git repository to Apify

If you've created a Git repository for the project, you can easily connect to Apify:

1. Go to [Actor creation page](https://console.apify.com/actors/new)
2. Click on **Link Git Repository** button

### Push project on your local machine to Apify

You can also deploy the project on your local machine to Apify without the need for the Git repository.

1. Log in to Apify. You will need to provide your [Apify API Token](https://console.apify.com/account/integrations) to complete this action.

    ```bash
    apify login
    ```

2. Deploy your Actor. This command will deploy and build the Actor on the Apify Platform. You can find your newly created Actor under [Actors -> My Actors](https://console.apify.com/actors?tab=my).

    ```bash
    apify push
    ```

## Documentation reference

To learn more about Apify and Actors, take a look at the following resources:

- [Apify SDK for JavaScript documentation](https://docs.apify.com/sdk/js)
- [Apify SDK for Python documentation](https://docs.apify.com/sdk/python)
- [Apify Platform documentation](https://docs.apify.com/platform)
- [Join our developer community on Discord](https://discord.com/invite/jyEM2PRvMU)
