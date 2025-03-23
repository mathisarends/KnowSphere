import textwrap
from langchain_core.prompts import ChatPromptTemplate

ASSESSMENT_PROMPT = textwrap.dedent("""
    Bewerte den folgenden Notion-Entwurf:

    TITEL: "{title}"
    INHALT:
    ---
    {content}
    ---

    Prüfe Vollständigkeit, Struktur, Formulierung und Aktualität des Inhalts.

    Entscheide:
    1. Muss der Entwurf überarbeitet werden? (Ja/Nein)
    2. Ist Web-Recherche nötig? (Sei hier zurückhaltend)
       - NUR wenn aktuelle/technische Details zwingend fehlen
       - NICHT recherchieren, wenn du die Informationen aus deinem Training ableiten kannst
       - NICHT für zeitlose, allgemeine oder gut dokumentierte Konzepte

    Antwortformat:
    BEWERTUNG: [Kurze Bewertung]
    ÜBERARBEITUNG NOTWENDIG: [Ja/Nein]
    ZUSÄTZLICHE INFORMATIONEN NOTWENDIG: [Ja/Nein]
    GRUND: [Knappe Begründung]
    """)

ASSESSMENT_PROMPT_TEMPLATE = ChatPromptTemplate.from_template(ASSESSMENT_PROMPT)

REVISION_PROMPT = textwrap.dedent("""
    Verbessere diesen Notion-Eintrag:

    TITEL: "{title}"
    INHALT:
    ---
    {content}
    ---

    Fokussiere dich auf:
    - Klare Struktur mit sinnvollen Überschriften
    - Präzise Formulierungen
    - Wichtige fehlende Informationen ergänzen
    - Markdown-Formatierung für bessere Lesbarkeit

    WICHTIG ZUM TITEL:
    - Behalte den Titel möglichst kompakt und originalnah
    - Ändere die Sprache des Titels NICHT (z.B. englische Fachbegriffe beibehalten)
    - Füge nur dann Erläuterungen hinzu, wenn es absolut notwendig ist

    Antwortformat:
    NEUER TITEL: [Kompakter Titel, nur minimale Änderungen wenn nötig]
    NEUER INHALT:
    [Überarbeiteter Inhalt in Markdown]
    ICON: [Passendes Emoji]
    """)

# Erweitertes Prompt für die Überarbeitung mit zusätzlichen Informationen
REVISION_WITH_SEARCH_PROMPT = textwrap.dedent("""
    Du bist ein KI-Assistent, der Notion-Einträge in einem Second Brain verbessert.

    KONTEXT:
    Der aktuelle Entwurf hat den Titel: "{title}"
    Der Inhalt lautet:
    ---
    {content}
    ---

    ZUSÄTZLICHE INFORMATIONEN AUS RECHERCHEN:
    ---
    {additional_info}
    ---

    AUFGABE:
    Erstelle eine verbesserte Version des Entwurfs. Behalte dabei das Hauptthema bei, aber verbessere:
    - Struktur (füge bei Bedarf Überschriften und Abschnitte hinzu)
    - Formulierung (mache den Text klarer und präziser)
    - Vollständigkeit (ergänze fehlende wichtige Informationen basierend auf der Recherche)
    - Formatierung (nutze Markdown für bessere Lesbarkeit)
    - Aktualität (integriere aktuelle Informationen aus der Recherche)

    Gib deine Antwort in diesem Format zurück:
    NEUER TITEL: [Der verbesserte Titel]
    NEUER INHALT:
    [Der vollständige überarbeitete Inhalt in Markdown-Format]
    ICON: [Ein passendes Emoji für das Thema des Eintrags]
    """)

REVISION_PROMPT_TEMPLATE = ChatPromptTemplate.from_template(REVISION_PROMPT)
REVISION_WITH_SEARCH_PROMPT_TEMPLATE = ChatPromptTemplate.from_template(REVISION_WITH_SEARCH_PROMPT)

def get_revision_prompt(has_additional_info=False):
    """Gibt das passende Revision-Prompt basierend auf dem Vorhandensein zusätzlicher Informationen zurück."""
    return REVISION_WITH_SEARCH_PROMPT_TEMPLATE if has_additional_info else REVISION_PROMPT_TEMPLATE