"""The upstreams the crawler pulls from.

Every byte of data that whereq.com did not type itself arrives through one
of these modules:

* :mod:`app.crawler.upstream.whereq_cloud` — the shared **whereq.cloud**
  client: one key, one rate limit, one retry policy. It is the account-wide
  budget every whereq.cloud feed shares.
* :mod:`app.crawler.upstream.fuel_stations` — fuel stations and their live
  prices, crawled from whereq.cloud and upserted into ``places``.
* :mod:`app.crawler.upstream.fuel_prices` — the aggregated price series
  (EIA / StatCan / CRE averages), also from whereq.cloud.
* :mod:`app.crawler.upstream.geo_places` — the administrative geography
  (provinces, cities, wards, neighbourhoods) with their outlines, crawled
  from whereq.cloud.
* :mod:`app.crawler.upstream.osm_places` — the OpenStreetMap POI layer,
  crawled from Overpass.

The content crawler — RSS and JSON sources for local news, events and
stories — lives one level up, in :mod:`app.crawler`, because it parses
feeds rather than calling a data API.
"""
