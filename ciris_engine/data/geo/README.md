# GeoNames Cities Database

This directory contains a SQLite database of world cities for the location typeahead feature.

## Database

- `cities.db` - SQLite database with ~33,000 cities (population > 15,000)
- Size: ~6MB
- Includes FTS5 full-text search index for fast typeahead

**Note:** The database is NOT committed to git. Regenerate it using:

```bash
python -m tools.build_geo_db
```

## Data Source

Data comes from [GeoNames](https://www.geonames.org/):
- cities15000.txt - Cities with population > 15,000
- admin1CodesASCII.txt - State/region names
- countryInfo.txt - Country names and currencies

## Database Schema

```sql
CREATE TABLE countries (
    code TEXT PRIMARY KEY,        -- ISO 3166-1 alpha-2
    name TEXT NOT NULL,
    currency_code TEXT,           -- ISO 4217
    currency_name TEXT,
    languages TEXT
);

CREATE TABLE admin1 (
    code TEXT PRIMARY KEY,        -- Format: "US.CA"
    name TEXT NOT NULL,
    country_code TEXT NOT NULL
);

CREATE TABLE cities (
    id INTEGER PRIMARY KEY,       -- GeoNames ID
    name TEXT NOT NULL,           -- Display name (may include Unicode)
    ascii_name TEXT NOT NULL,     -- ASCII-only name
    country_code TEXT NOT NULL,
    admin1_code TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    population INTEGER NOT NULL,
    timezone TEXT
);

-- FTS5 virtual table for fast text search
CREATE VIRTUAL TABLE cities_fts USING fts5(name, ascii_name, content='cities');
```

## License

GeoNames data is licensed under [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
