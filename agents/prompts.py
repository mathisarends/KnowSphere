import textwrap


ASSESSMENT_PROMPT = textwrap.dedent("""
    Du bist ein KI-Assistent, der Notion-Einträge in einem Second Brain bewertet und verbessert.

    KONTEXT:
    Der aktuelle Entwurf hat den Titel: "{title}"
    Der Inhalt lautet:
    ---
    {content}
    ---

    AUFGABE:
    1. Bewerte den Entwurf hinsichtlich folgender Kriterien:
    - Vollständigkeit: Ist der Inhalt vollständig oder fehlen wichtige Informationen?
    - Struktur: Ist der Inhalt gut strukturiert?
    - Formulierung: Ist der Text klar und präzise formuliert?
    - Aktuelle Relevanz: Ist der Inhalt noch aktuell und relevant?

    2. Entscheide, ob der Entwurf überarbeitet werden sollte.
    - Bei minimalen Mängeln: Keine Überarbeitung notwendig
    - Bei deutlichen Mängeln: Überarbeitung empfehlen

    Gib deine Bewertung in diesem Format zurück:
    BEWERTUNG: [Deine Bewertung]
    ÜBERARBEITUNG NOTWENDIG: [Ja/Nein]
    GRUND: [Erklärung deiner Entscheidung]
    """)

REVISION_PROMPT = textwrap.dedent("""
    Du bist ein KI-Assistent, der Notion-Einträge in einem Second Brain verbessert.

    KONTEXT:
    Der aktuelle Entwurf hat den Titel: "{title}"
    Der Inhalt lautet:
    ---
    {content}
    ---

    AUFGABE:
    Erstelle eine verbesserte Version des Entwurfs. Behalte dabei das Hauptthema bei, aber verbessere:
    - Struktur (füge bei Bedarf Überschriften und Abschnitte hinzu)
    - Formulierung (mache den Text klarer und präziser)
    - Vollständigkeit (ergänze fehlende wichtige Informationen, soweit erkennbar)
    - Formatierung (nutze Markdown für bessere Lesbarkeit)

    Gib deine Antwort in diesem Format zurück:
    NEUER TITEL: [Der verbesserte Titel]
    NEUER INHALT:
    [Der vollständige überarbeitete Inhalt in Markdown-Format]
    ICON: [Ein passendes Emoji für das Thema des Eintrags]
    """)