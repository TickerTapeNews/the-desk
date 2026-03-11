"""
Hämtar pressmeddelanden från Europawire RSS-feed och sparar i Turso-databas.
"""

import os
import sys
import feedparser
import libsql_experimental as libsql


def get_db_connection():
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")
    if not url or not token:
        print("FEL: TURSO_DATABASE_URL och TURSO_AUTH_TOKEN måste vara satta.")
        sys.exit(1)
    conn = libsql.connect("local.db", sync_url=url, auth_token=token)
    conn.sync()
    return conn


def ensure_tables(conn):
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
            processed INTEGER DEFAULT 0,
            source TEXT DEFAULT 'europawire'
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


def fetch_and_store(conn):
    feed_url = "https://news.europawire.eu/feed/"
    print(f"Hämtar RSS från {feed_url}...")
    feed = feedparser.parse(feed_url)

    if feed.bozo and not feed.entries:
        print(f"FEL: Kunde inte parsa RSS-feeden: {feed.bozo_exception}")
        sys.exit(1)

    print(f"Hittade {len(feed.entries)} poster i feeden.")
    new_count = 0

    for entry in feed.entries:
        guid = entry.get("id") or entry.get("link") or entry.get("title")
        if not guid:
            continue

        title = entry.get("title", "Utan titel")
        link = entry.get("link", "")
        pub_date = entry.get("published", "")
        description = entry.get("summary", "")

        content = ""
        if hasattr(entry, "content") and entry.content:
            content = entry.content[0].get("value", "")
        elif description:
            content = description

        try:
            conn.execute(
                """INSERT INTO press_releases (guid, title, link, pub_date, description, content, source)
                VALUES (?, ?, ?, ?, ?, ?, 'europawire')""",
                (guid, title, link, pub_date, description, content),
            )
            new_count += 1
            print(f"  NY: {title[:80]}")
        except Exception as e:
            if "UNIQUE" in str(e).upper():
                pass
            else:
                print(f"  FEL vid insättning av '{title[:50]}': {e}")

    conn.commit()
    conn.sync()
    print(f"\nKlart! {new_count} nya pressmeddelanden sparade.")


def main():
    conn = get_db_connection()
    ensure_tables(conn)
    fetch_and_store(conn)


if __name__ == "__main__":
    main()
