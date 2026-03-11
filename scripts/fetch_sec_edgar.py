"""
Hämtar 8-K filings från SEC EDGAR Atom-feed.
Steg:
1. Parsa Atom-feeden
2. Hämta länken i varje entry
3. Byt ut -index.htm till .txt
4. Hämta .txt-filens innehåll
5. Spara i Turso-databasen
"""

import os
import sys
import time
import httpx
import feedparser
import libsql_experimental as libsql
from datetime import datetime, timezone


# SEC kräver User-Agent med kontaktinfo
SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "TickerTapeNews/1.0 (contact@tickertapenews.com)"
)

EDGAR_FEED_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=8-K&count=40&owner=include&output=atom"
)


def get_db_connection():
    """Anslut till Turso-databasen."""
    url = os.environ.get("TURSO_DATABASE_URL")
    token = os.environ.get("TURSO_AUTH_TOKEN")

    if not url or not token:
        print("FEL: TURSO_DATABASE_URL och TURSO_AUTH_TOKEN måste vara satta.")
        sys.exit(1)

    conn = libsql.connect("local.db", sync_url=url, auth_token=token)
    conn.sync()
    return conn


def ensure_tables(conn):
    """Skapa tabeller om de inte finns (samma som Europawire använder)."""
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
    conn.commit()
    conn.sync()


def index_url_to_txt_url(index_url):
    """
    Konvertera EDGAR index-URL till .txt-URL.
    Exempel:
      .../000123456-25-000789-index.htm → .../000123456-25-000789.txt
    """
    if not index_url:
        return None

    # Hantera olika varianter
    if "-index.htm" in index_url:
        return index_url.replace("-index.htm", ".txt")
    elif "-index.html" in index_url:
        return index_url.replace("-index.html", ".txt")

    return None


def fetch_filing_content(client, txt_url):
    """Hämta innehållet i en .txt filing från EDGAR."""
    try:
        response = client.get(
            txt_url,
            headers={"User-Agent": SEC_USER_AGENT},
            timeout=30,
        )
        response.raise_for_status()

        content = response.text

        # Begränsa storlek – 8-K filings kan vara enorma
        if len(content) > 50000:
            content = content[:50000] + "\n\n[TRUNCATED - full filing at SEC.gov]"

        return content

    except Exception as e:
        print(f"    FEL vid hämtning av {txt_url}: {e}")
        return None


def fetch_and_store(conn):
    """Hämta EDGAR Atom-feed och spara nya filings."""
    print(f"Hämtar SEC EDGAR 8-K feed...")

    # Parsa Atom-feeden
    feed = feedparser.parse(
        EDGAR_FEED_URL,
        request_headers={"User-Agent": SEC_USER_AGENT},
    )

    if feed.bozo and not feed.entries:
        print(f"FEL: Kunde inte parsa EDGAR-feeden: {feed.bozo_exception}")
        return

    print(f"Hittade {len(feed.entries)} poster i EDGAR-feeden.")

    # Skapa HTTP-klient med SEC User-Agent
    client = httpx.Client(
        headers={"User-Agent": SEC_USER_AGENT},
        follow_redirects=True,
    )

    new_count = 0

    for entry in feed.entries:
        # EDGAR Atom entries har en unik id
        guid = entry.get("id") or entry.get("link", {})

        # Hämta länk – kan vara en lista av link-objekt i Atom
        link = ""
        if hasattr(entry, "links") and entry.links:
            for lnk in entry.links:
                if lnk.get("type", "") == "text/html" or lnk.get("rel") == "alternate":
                    link = lnk.get("href", "")
                    break
            if not link:
                link = entry.links[0].get("href", "")
        elif hasattr(entry, "link"):
            link = entry.link

        if not guid:
            guid = link

        if not guid:
            continue

        title = entry.get("title", "SEC 8-K Filing")
        pub_date = entry.get("updated", entry.get("published", ""))
        summary = entry.get("summary", "")

        # Kolla om vi redan har denna filing
        existing = conn.execute(
            "SELECT id FROM press_releases WHERE guid = ?", (guid,)
        ).fetchone()

        if existing:
            continue

        # Konvertera index-URL till .txt-URL och hämta innehåll
        txt_url = index_url_to_txt_url(link)
        content = ""

        if txt_url:
            print(f"  Hämtar filing: {txt_url[:80]}...")
            content = fetch_filing_content(client, txt_url) or ""
            # Var snäll mot SEC:s servrar
            time.sleep(0.5)
        else:
            content = summary

        # Spara i databasen
        try:
            conn.execute(
                """
                INSERT INTO press_releases (guid, title, link, pub_date, description, content, source)
                VALUES (?, ?, ?, ?, ?, ?, 'sec_edgar')
                """,
                (guid, title, link, pub_date, summary, content),
            )
            new_count += 1
            print(f"  NY: {title[:80]}")
        except Exception as e:
            if "UNIQUE" in str(e).upper():
                pass
            else:
                print(f"  FEL vid insättning: {e}")

    client.close()
    conn.commit()
    conn.sync()
    print(f"\nKlart! {new_count} nya SEC 8-K filings sparade.")


def main():
    conn = get_db_connection()
    ensure_tables(conn)
    fetch_and_store(conn)


if __name__ == "__main__":
    main()
