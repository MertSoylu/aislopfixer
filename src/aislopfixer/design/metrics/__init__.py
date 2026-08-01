"""Measurement modules — each answers one question about the distribution.

Every module here exposes ``analyze(docs)`` and returns observations plus the
repetition contribution for its axis. They never mutate the documents and never
talk to each other, so a metric can be added, removed or recalibrated without
touching the rest.
"""
