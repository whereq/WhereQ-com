"""The whereq.com crawler — the app's retrieval layer.

Nothing that whereq.com shows on the map is typed by hand. Every place,
price, outline and headline arrives by being **crawled** from an upstream:

============================  ===========================================
Upstream                      What the crawler pulls
============================  ===========================================
**whereq.cloud**              fuel stations, live prices, the aggregated
                              price series, and the administrative
                              geography (provinces, cities, wards,
                              neighbourhoods) with their outlines
**OpenStreetMap**             the POI layer — coffee, food, parking, shops
**RSS / JSON feeds**           local news, events, stories and topics
============================  ===========================================

The crawl has three layers:

* :mod:`app.crawler.upstream` — one module per upstream. Where the bytes
  come from, and how they are parsed into rows.
* the content crawler (:mod:`app.crawler.pipeline`, :mod:`app.crawler.rss`,
  :mod:`app.crawler.json_source`) — discovers items from the registered
  ``news_source`` definitions, normalizes them, places them on the map,
  classifies them and upserts ``local_content`` rows.
* :mod:`app.crawler.scheduler` — the long-running loop that decides what is
  due, and crawls it. It also drives the whereq.cloud and OpenStreetMap
  crawls, so the whole retrieval layer is one process with one cadence.

Entry points:

    python -m app.crawler.scheduler        # the loop (the container's command)
    python -m app.crawler.run              # one content crawl, by hand
    python -m app.crawler.cli.fuel         # one whereq.cloud fuel crawl
    python -m app.crawler.cli.geo          # one whereq.cloud geography crawl
    python -m app.crawler.cli.places       # one OpenStreetMap POI crawl

The whereq.cloud API key (``WHEREQ_CLOUD_API_KEY``) is read from the
environment and never reaches the browser — the crawler runs server-side,
and the app serves what it crawled from its own API.
"""
