"""
Genererar en RSS/Atom XML-feed från sammanfattade nyheter i Turso.
Publiceras sedan via GitHub Pages.
Körs var 15:e minut via GitHub Actions.
"""

import os
import sys
import libsql_experimental as libsql
from datetime import datetime, timezone
import xml.etree.ElementTree as ET


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


def get_recent_summaries(conn, limit=50):
    """Hämta de senaste sammanfattningarna."""
    result = conn.execute(
        """
        SELECT
            s.title,
            s.summary,
            s.impact_score,
            s.isin,
            s.created_at,
            pr.link,
            pr.pub_date,
            pr.guid
        FROM summaries s
        JOIN press_releases pr ON s.press_release_id = pr.id
        ORDER BY s.created_at DESC
        LIMIT ?
        """,
        (limit,),
    )
    rows = result.fetchall()
    return [
        {
            "title": row[0],
            "summary": row[1],
            "impact_score": row[2],
            "isin": row[3],
            "created_at": row[4],
            "link": row[5],
            "pub_date": row[6],
            "guid": row[7],
        }
        for row in rows
    ]


def format_rfc822(date_str):
    """Konvertera datum till RFC 822 format för RSS."""
    if not date_str:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    try:
        # Försök parsa ISO-format
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except (ValueError, AttributeError):
        return date_str


def generate_rss_feed(summaries, output_dir="public"):
    """Generera RSS 2.0 XML-feed."""
    rss = ET.Element("rss", version="2.0")
    rss.set("xmlns:atom", "http://www.w3.org/2005/Atom")

    channel = ET.SubElement(rss, "channel")

    # Channel metadata
    ET.SubElement(channel, "title").text = "Europawire News - AI-sammanfattade pressmeddelanden"
    ET.SubElement(channel, "description").text = (
        "Automatiskt sammanfattade europeiska pressmeddelanden "
        "med impact score och ISIN, genererade med Claude AI. "
        "Relevanta för investerare."
    )
    ET.SubElement(channel, "language").text = "sv"
    ET.SubElement(channel, "lastBuildDate").text = format_rfc822(
        datetime.now(timezone.utc).isoformat()
    )
    ET.SubElement(channel, "generator").text = "Europawire News Generator"

    # Items
    for item_data in summaries:
        item = ET.SubElement(channel, "item")

        # Titel med impact score
        impact = item_data.get("impact_score", 0)
        impact_label = "⚡" * min(impact, 5)
        title_text = f"[Impact {impact}/5 {impact_label}] {item_data['title']}"
        ET.SubElement(item, "title").text = title_text

        # Beskrivning med sammanfattning, ISIN och impact
        isin = item_data.get("isin", "unlisted")
        description_parts = [
            item_data["summary"],
            f"\n\n📊 Impact Score: {impact}/5",
            f"🏷️ ISIN: {isin}",
        ]
        if item_data.get("link"):
            description_parts.append(f"🔗 Källa: {item_data['link']}")

        ET.SubElement(item, "description").text = "\n".join(description_parts)

        if item_data.get("link"):
            ET.SubElement(item, "link").text = item_data["link"]

        if item_data.get("guid"):
            guid_elem = ET.SubElement(item, "guid", isPermaLink="false")
            guid_elem.text = f"europawire-summary-{item_data['guid']}"

        pub_date = item_data.get("created_at") or item_data.get("pub_date")
        ET.SubElement(item, "pubDate").text = format_rfc822(pub_date)

        # Kategorier
        ET.SubElement(item, "category").text = f"impact-{impact}"
        if isin and isin != "unlisted":
            ET.SubElement(item, "category").text = f"isin-{isin}"

    # Skriv till fil
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "feed.xml")

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)

    with open(output_path, "wb") as f:
        tree.write(f, encoding="UTF-8", xml_declaration=True)

    print(f"RSS-feed genererad: {output_path} ({len(summaries)} poster)")
    return output_path


def generate_atom_feed(summaries, output_dir="public"):
    """Generera Atom 1.0 XML-feed som alternativ."""
    ns = "http://www.w3.org/2005/Atom"
    feed = ET.Element("feed", xmlns=ns)

    ET.SubElement(feed, "title").text = "Europawire News - AI-sammanfattade pressmeddelanden"
    ET.SubElement(feed, "subtitle").text = (
        "Automatiskt sammanfattade europeiska pressmeddelanden för investerare"
    )
    ET.SubElement(feed, "updated").text = datetime.now(timezone.utc).isoformat()

    author = ET.SubElement(feed, "author")
    ET.SubElement(author, "name").text = "Europawire News Bot"

    ET.SubElement(feed, "id").text = "urn:europawire-news-feed"

    for item_data in summaries:
        entry = ET.SubElement(feed, "entry")

        impact = item_data.get("impact_score", 0)
        ET.SubElement(entry, "title").text = f"[Impact {impact}/5] {item_data['title']}"

        if item_data.get("link"):
            ET.SubElement(entry, "link", href=item_data["link"])

        guid = item_data.get("guid", str(item_data.get("created_at", "")))
        ET.SubElement(entry, "id").text = f"urn:europawire-summary:{guid}"

        pub_date = item_data.get("created_at") or item_data.get("pub_date", "")
        try:
            ET.SubElement(entry, "updated").text = datetime.fromisoformat(
                pub_date.replace("Z", "+00:00")
            ).isoformat()
        except (ValueError, AttributeError):
            ET.SubElement(entry, "updated").text = datetime.now(timezone.utc).isoformat()

        isin = item_data.get("isin", "unlisted")
        content_text = (
            f"{item_data['summary']}\n\n"
            f"Impact Score: {impact}/5 | ISIN: {isin}"
        )
        content_elem = ET.SubElement(entry, "content", type="text")
        content_elem.text = content_text

    # Skriv till fil
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "atom.xml")

    tree = ET.ElementTree(feed)
    ET.indent(tree, space="  ", level=0)

    with open(output_path, "wb") as f:
        tree.write(f, encoding="UTF-8", xml_declaration=True)

    print(f"Atom-feed genererad: {output_path} ({len(summaries)} poster)")
    return output_path


def main():
    conn = get_db_connection()
    summaries = get_recent_summaries(conn)

    if not summaries:
        print("Inga sammanfattningar att publicera.")
        # Skapa tom feed ändå så att GitHub Pages inte kraschar
        summaries = []

    generate_rss_feed(summaries)
    generate_atom_feed(summaries)


if __name__ == "__main__":
    main()
