# Europawire News - Automatiserad nyhetsgenerering

Automatiserat flöde som:
1. Hämtar pressmeddelanden från Europawire RSS-feed var 5:e minut
2. Sammanfattar dem med Claude Haiku (investerar-perspektiv, impact score, ISIN)
3. Publicerar en egen RSS/Atom-feed via GitHub Pages

## Setup-guide (steg för steg)

### 1. Skapa Turso-databas

1. Logga in på https://turso.tech/
2. Skapa en ny databas (t.ex. `europawire`)
3. Kopiera databasens URL – den ser ut som:
   ```
   libsql://europawire-dittanvändarnamn.turso.io
   ```
4. Skapa en auth token via Turso dashboard (under "Tokens" / "Create Token")

### 2. Skapa databas-tabellerna

Gå till din Turso dashboard → din databas → "Shell" (eller "Edit Data") och kör:

```sql
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
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    press_release_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    impact_score INTEGER NOT NULL,
    isin TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (press_release_id) REFERENCES press_releases(id)
);
```

### 3. Skaffa Anthropic API-nyckel

1. Gå till https://console.anthropic.com/
2. Skapa konto eller logga in
3. Settings → API Keys → Create Key
4. Kopiera nyckeln

### 4. Lägg till secrets i GitHub

Gå till ditt GitHub-repo → Settings → Secrets and variables → Actions → New repository secret

Lägg till dessa tre:

| Namn | Värde |
|------|-------|
| `TURSO_DATABASE_URL` | Din Turso-databas-URL |
| `TURSO_AUTH_TOKEN` | Din Turso auth token |
| `ANTHROPIC_API_KEY` | Din Anthropic API-nyckel |

### 5. Aktivera GitHub Pages

1. Gå till repo Settings → Pages
2. Under "Source" välj **GitHub Actions**

### 6. Ladda upp filerna

Ladda upp alla filer från detta paket till ditt GitHub-repo. Behåll mappstrukturen exakt som den är.

### 7. Klart!

GitHub Actions kommer automatiskt att:
- Var 5:e minut: Hämta nya pressmeddelanden från Europawire
- Var 10:e minut: Sammanfatta nya pressmeddelanden med Claude Haiku
- Var 15:e minut: Uppdatera den publika RSS-feeden

Din RSS-feed blir tillgänglig på:
```
https://DITT-ANVÄNDARNAMN.github.io/REPO-NAMN/feed.xml
```

## Filstruktur

```
.github/
  workflows/
    fetch-rss.yml          # Hämtar pressmeddelanden var 5:e minut
    summarize.yml          # Sammanfattar med Claude Haiku var 10:e minut
    publish-feed.yml       # Publicerar RSS-feed var 15:e minut
scripts/
    fetch_rss.py           # Hämtar och sparar pressmeddelanden
    summarize.py           # Anropar Claude Haiku för sammanfattningar
    generate_feed.py       # Genererar RSS/Atom XML
    init_db.py             # Skapar databas-tabeller (backup)
    cleanup.py             # Rensar gamla pressmeddelanden (7 dagar)
public/
    index.html             # Enkel landningssida för GitHub Pages
requirements.txt           # Python-beroenden
```

## Kostnad

- **GitHub Actions**: Gratis (2000 min/månad på free tier)
- **Turso**: Gratis tier räcker gott
- **Claude Haiku**: ~$0.001 per sammanfattning (mycket billigt)

Vid ~50 pressmeddelanden/dag ≈ ca 5-15 kr/månad för Anthropic API.
