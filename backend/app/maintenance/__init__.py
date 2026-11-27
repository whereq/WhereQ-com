"""Maintenance commands — the work the app needs but nothing schedules.

Right now one command lives here:

    python -m app.maintenance.reindex

It rebuilds the spatial indexes that the upstream's weekly rewrite bloats.
It is **not** run by the scheduler: it is a deliberate operation, and the
tool decides what is worth rebuilding by measuring, not by guessing.
"""
