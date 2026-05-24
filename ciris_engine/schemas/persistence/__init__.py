"""Persistence schemas.

The active runtime schema is owned entirely by ciris-persist (the
`cirislens.*` / `cirisgraph.*` tables created by persist's own sqlx
migrations). The legacy 2.8.x table-DDL constants that used to live in
`sqlite/tables.py` + `postgres/tables.py` were removed in 2.9.0 along
with the SQLite bootstrap layer — nothing in the agent issues CREATE
TABLE anymore.

`core.py` and `correlations.py` here remain: they hold the Pydantic
request/response models for the persistence layer, not table DDL.
"""
