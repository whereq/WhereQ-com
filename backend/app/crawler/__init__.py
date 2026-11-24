"""WhereQ local-content crawler.

Discovers news / events / stories / topics from registered ``news_source``
definitions, normalizes them, geocodes a location, classifies a category, and
upserts ``local_content`` rows for display on the map.

Entry point:  ``python -m app.crawler.run``  (cron-driven on PROD).
"""
