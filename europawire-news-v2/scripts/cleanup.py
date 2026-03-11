"""
Rensar pressmeddelanden och sammanfattningar äldre än 7 dagar.
Körs en gång per dag via GitHub Actions.
"""

import os
import sys
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


def cleanup(conn):
    """Ta bort poster äldre än 7 dagar."""
    # Ta bort sammanfattningar kopplade till gamla pressmeddelanden
    result1 = conn.execute("""
        DELETE FROM summaries
        WHERE press_release_id IN (
            SELECT id FROM press_releases
            WHERE fetched_at < datetime('now', '-7 days')
        )
    """)

    # Ta bort gamla pressmeddelanden
    result2 = conn.execute("""
        DELETE FROM press_releases
        WHERE fetched_at < datetime('now', '-7 days')
    """)

    conn.commit()
    conn.sync()

    print(f"Rensning klar. Borttagna poster äldre än 7 dagar.")


def main():
    conn = get_db_connection()
    cleanup(conn)


if __name__ == "__main__":
    main()
