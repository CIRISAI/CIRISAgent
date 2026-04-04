#!/usr/bin/env python3
"""Build SQLite database from GeoNames cities15000 data.

Usage:
    python -m tools.build_geo_db

Creates ciris_engine/data/geo/cities.db with:
- cities table: ~26K cities with population > 15,000
- admin1 table: states/regions
- countries table: country names and codes
"""

import sqlite3
from pathlib import Path

GEO_DIR = Path(__file__).parent.parent / "ciris_engine" / "data" / "geo"
DB_PATH = GEO_DIR / "cities.db"
CITIES_FILE = GEO_DIR / "cities15000.txt"
ADMIN1_FILE = GEO_DIR / "admin1CodesASCII.txt"
COUNTRY_FILE = GEO_DIR / "countryInfo.txt"


def build_database() -> None:
    """Build the cities database from GeoNames data."""
    # Remove existing database
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Create tables
    cursor.execute(
        """
        CREATE TABLE countries (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            currency_code TEXT,
            currency_name TEXT,
            languages TEXT
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE admin1 (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            country_code TEXT NOT NULL
        )
    """
    )

    cursor.execute(
        """
        CREATE TABLE cities (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            ascii_name TEXT NOT NULL,
            country_code TEXT NOT NULL,
            admin1_code TEXT,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            population INTEGER NOT NULL,
            timezone TEXT,
            FOREIGN KEY (country_code) REFERENCES countries(code)
        )
    """
    )

    # Create indexes for fast search
    cursor.execute("CREATE INDEX idx_cities_name ON cities(name COLLATE NOCASE)")
    cursor.execute("CREATE INDEX idx_cities_ascii ON cities(ascii_name COLLATE NOCASE)")
    cursor.execute("CREATE INDEX idx_cities_country ON cities(country_code)")
    cursor.execute("CREATE INDEX idx_cities_population ON cities(population DESC)")

    # Load countries
    print("Loading countries...")
    country_count = 0
    with open(COUNTRY_FILE, encoding="utf-8") as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            parts = line.strip().split("\t")
            if len(parts) >= 15:
                code = parts[0]
                name = parts[4]
                currency_code = parts[10] if len(parts) > 10 else ""
                currency_name = parts[11] if len(parts) > 11 else ""
                languages = parts[15] if len(parts) > 15 else ""
                cursor.execute(
                    "INSERT OR IGNORE INTO countries (code, name, currency_code, currency_name, languages) VALUES (?, ?, ?, ?, ?)",
                    (code, name, currency_code, currency_name, languages),
                )
                country_count += 1
    print(f"  Loaded {country_count} countries")

    # Load admin1 codes (states/regions)
    print("Loading admin1 codes...")
    admin1_count = 0
    with open(ADMIN1_FILE, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 2:
                code = parts[0]  # Format: "US.CA"
                name = parts[1]
                country_code = code.split(".")[0] if "." in code else ""
                cursor.execute(
                    "INSERT OR IGNORE INTO admin1 (code, name, country_code) VALUES (?, ?, ?)",
                    (code, name, country_code),
                )
                admin1_count += 1
    print(f"  Loaded {admin1_count} admin1 codes")

    # Load cities
    print("Loading cities...")
    city_count = 0
    with open(CITIES_FILE, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 15:
                geoname_id = int(parts[0])
                name = parts[1]
                ascii_name = parts[2]
                latitude = float(parts[4])
                longitude = float(parts[5])
                country_code = parts[8]
                admin1_code = f"{country_code}.{parts[10]}" if parts[10] else None
                population = int(parts[14]) if parts[14] else 0
                timezone = parts[17] if len(parts) > 17 else None

                cursor.execute(
                    """INSERT INTO cities (id, name, ascii_name, country_code, admin1_code, latitude, longitude, population, timezone)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        geoname_id,
                        name,
                        ascii_name,
                        country_code,
                        admin1_code,
                        latitude,
                        longitude,
                        population,
                        timezone,
                    ),
                )
                city_count += 1
    print(f"  Loaded {city_count} cities")

    # Create FTS5 virtual table for fast text search
    print("Creating FTS5 search index...")
    cursor.execute(
        """
        CREATE VIRTUAL TABLE cities_fts USING fts5(
            name,
            ascii_name,
            content='cities',
            content_rowid='id'
        )
    """
    )

    # Populate FTS table
    cursor.execute(
        """
        INSERT INTO cities_fts(rowid, name, ascii_name)
        SELECT id, name, ascii_name FROM cities
    """
    )

    conn.commit()

    # Report stats
    cursor.execute("SELECT COUNT(*) FROM cities")
    total_cities = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM countries")
    total_countries = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM admin1")
    total_admin1 = cursor.fetchone()[0]

    print(f"\nDatabase created at: {DB_PATH}")
    print(f"  Cities: {total_cities:,}")
    print(f"  Countries: {total_countries}")
    print(f"  Admin1 regions: {total_admin1:,}")

    # Check file size
    db_size = DB_PATH.stat().st_size
    print(f"  Database size: {db_size / 1024 / 1024:.2f} MB")

    conn.close()


if __name__ == "__main__":
    build_database()
