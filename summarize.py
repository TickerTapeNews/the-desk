"""
Hämtar obearbetade pressmeddelanden från Turso och sammanfattar dem med Claude Haiku.
Sparar sammanfattningar tillbaka i databasen.
Körs var 10:e minut via GitHub Actions.
"""

import os
import sys
import json
import libsql_experimental as libsql
from anthropic import Anthropic


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


def get_unprocessed(conn, limit=10):
    """Hämta pressmeddelanden som inte har sammanfattats ännu."""
    result = conn.execute(
        """
        SELECT id, title, content, description, link
        FROM press_releases
        WHERE processed = 0
        ORDER BY fetched_at ASC
        LIMIT ?
        """,
        (limit,),
    )
    rows = result.fetchall()
    return [
        {
            "id": row[0],
            "title": row[1],
            "content": row[2] or row[3] or "",
            "link": row[4] or "",
        }
        for row in rows
    ]


def summarize_with_claude(client, press_release):
    """Skicka pressmeddelande till Claude Haiku för sammanfattning."""
    title = press_release["title"]
    content = press_release["content"]

    # Begränsa innehållet för att spara tokens
    if len(content) > 8000:
        content = content[:8000] + "..."

    prompt = f"""Du är en finansnyhetsjournalist. Analysera följande pressmeddelande och returnera ett JSON-objekt.

PRESSMEDDELANDE:
Titel: {title}
Innehåll: {content}

INSTRUKTIONER:
1. Sammanfatta innehållet till en kort nyhetsartikel, relevant för en investerare. Max 700 tecken.
2. Skapa en titel som gärna liknar ursprungstiteln men är anpassad som nyhetsrubrik.
3. Ge ett "impact_score" från 1-5 där högre = mer förväntad kurspåverkan.
   - 1 = Rutinmässigt/låg påverkan (t.ex. eventdeltagande, mindre uppdateringar)
   - 2 = Viss relevans (t.ex. nya partnerskap, produktuppdateringar)
   - 3 = Märkbar potentiell påverkan (t.ex. nya kontrakt, expansioner)
   - 4 = Betydande påverkan (t.ex. stora förvärv, resultatvarningar)
   - 5 = Mycket hög påverkan (t.ex. fusioner, VD-byten, vinstvarningar)
4. Ange ISIN-nummer för bolaget som är avsändare. Om du inte vet ISIN eller om bolaget inte är listat på en europeisk börs, ange "unlisted".

Svara ENBART med ett JSON-objekt i detta format (ingen annan text):
{{
    "title": "Nyhetsrubrik här",
    "summary": "Sammanfattning här (max 700 tecken)",
    "impact_score": 3,
    "isin": "SE0000000001 eller unlisted"
}}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        response_text = response.content[0].text.strip()

        # Rensa eventuella markdown code blocks
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

        result = json.loads(response_text)

        # Validera
        assert "title" in result, "Saknar 'title'"
        assert "summary" in result, "Saknar 'summary'"
        assert "impact_score" in result, "Saknar 'impact_score'"
        assert isinstance(result["impact_score"], int), "impact_score måste vara int"
        assert 1 <= result["impact_score"] <= 5, "impact_score måste vara 1-5"

        # Begränsa sammanfattning till 700 tecken
        if len(result["summary"]) > 700:
            result["summary"] = result["summary"][:697] + "..."

        result.setdefault("isin", "unlisted")

        return result

    except json.JSONDecodeError as e:
        print(f"  FEL: Kunde inte parsa JSON från Claude: {e}")
        print(f"  Svar: {response_text[:200]}")
        return None
    except Exception as e:
        print(f"  FEL vid Claude-anrop: {e}")
        return None


def process_press_releases(conn, client):
    """Bearbeta alla obearbetade pressmeddelanden."""
    unprocessed = get_unprocessed(conn)

    if not unprocessed:
        print("Inga nya pressmeddelanden att bearbeta.")
        return

    print(f"Bearbetar {len(unprocessed)} pressmeddelanden...")

    for pr in unprocessed:
        print(f"\n  Sammanfattar: {pr['title'][:70]}...")
        result = summarize_with_claude(client, pr)

        if result:
            try:
                conn.execute(
                    """
                    INSERT INTO summaries (press_release_id, title, summary, impact_score, isin)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        pr["id"],
                        result["title"],
                        result["summary"],
                        result["impact_score"],
                        result.get("isin", "unlisted"),
                    ),
                )

                conn.execute(
                    "UPDATE press_releases SET processed = 1 WHERE id = ?",
                    (pr["id"],),
                )

                conn.commit()
                conn.sync()
                print(f"    ✓ Sparat (impact: {result['impact_score']}, isin: {result.get('isin', 'unlisted')})")

            except Exception as e:
                print(f"    FEL vid databasinsättning: {e}")
        else:
            print(f"    ✗ Sammanfattning misslyckades, försöker igen nästa körning")


def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("FEL: ANTHROPIC_API_KEY måste vara satt.")
        sys.exit(1)

    client = Anthropic(api_key=api_key)
    conn = get_db_connection()
    process_press_releases(conn, client)


if __name__ == "__main__":
    main()
