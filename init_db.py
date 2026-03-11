"""
Skapar databas-tabeller i Turso. Kan köras manuellt om tabellerna
inte redan skapats via Turso dashboard.
"""

import os
import sys
import libsql_experimental as libsql


def main():
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")

    if not url or not token:
        print("FEL: TURSO_DATABASE_URL och TURSO_AUTH_TOKEN måste vara satta.")
        sys.exit(1)

    conn = libsql.connect("local.db", sync_url=url, auth_token=token)
    conn.sync()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS press_releases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            link TEXT,
            pub_date TEXT,
            description TEXT,
            content TEXT,
            fetched_at TEXT DEFAULT (datetime('now')),
            processed INTEGER DEFAULT 0
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            press_release_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            impact_score INTEGER NOT NULL,
            isin TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (press_release_id) REFERENCES press_releases(id)
        )
    """)

    conn.commit()
    conn.sync()
    print("Tabeller skapade!")


if __name__ == "__main__":
    main()
