"""Integration-test package marker.

Database fixtures (`engine`, `db_session`, `registered_sources`) live in
``tests/conftest.py`` so end-to-end tests can share them without duplicate
pytest plugin registration.
"""
