"""Command-line entry points for the crawler.

Each module crawls one upstream and writes it into the database:

    python -m app.crawler.cli.fuel      # whereq.cloud fuel stations + prices
    python -m app.crawler.cli.geo       # whereq.cloud administrative geography
    python -m app.crawler.cli.places    # OpenStreetMap POIs
    python -m app.crawler.run           # the RSS/JSON content crawler

The scheduler (``python -m app.crawler.scheduler``) does the same work on a
timer; these CLIs are for running a crawl once, by hand, on demand.
"""
