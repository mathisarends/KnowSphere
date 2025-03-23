import textwrap
from typing import List
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Definiere Datenmodelle für strukturierte Ausgaben
class AssessmentResult(BaseModel):
    """Ergebnis der Bewertung eines Notion-Entwurfs."""
    needs_revision: bool = Field(description="Gibt an, ob der Entwurf überarbeitet werden muss")
    requires_search: bool = Field(description="Gibt an, ob zusätzliche Informationen benötigt werden")
    assessment: str = Field(description="Kurze Bewertung des Entwurfs")
    reason: str = Field(description="Begründung für die Entscheidung")

class RevisionResult(BaseModel):
    title: str = Field(description="Der neue Titel des Eintrags")
    content: str = Field(description="Der überarbeitete Inhalt in Markdown")
    icon: str = Field(description="Ein passendes Emoji für den Eintrag")

class ReferencesResult(BaseModel):
    projects: List[str] = Field(description="Liste passender Projekte aus den verfügbaren Optionen")
    topics: List[str] = Field(description="Liste passender Themen aus den verfügbaren Optionen")

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

    Gib deine Antwort als JSON-Objekt mit folgenden Feldern zurück:
    - needs_revision: Boolean (true/false)
    - requires_search: Boolean (true/false)
    - assessment: String mit kurzer Bewertung
    - reason: String mit knapper Begründung
    """)

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

    WICHTIG ZUM INHALT:
    - Wiederhole NICHT den Titel am Anfang des Inhalts
    - Beginne den Inhalt direkt mit dem relevanten Text oder einer Einführung
    - Starte nicht mit einer Überschrift, die den Titel wiederholt

    Gib deine Antwort als JSON-Objekt mit folgenden Feldern zurück:
    - title: String mit dem neuen Titel
    - content: String mit dem überarbeiteten Inhalt in Markdown (ohne Wiederholung des Titels)
    - icon: String mit einem passenden Emoji
    """)

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

    WICHTIG ZUM TITEL:
    - Behalte den Titel möglichst kompakt und originalnah
    - Ändere die Sprache des Titels NICHT (z.B. englische Fachbegriffe beibehalten)
    
    WICHTIG ZUM INHALT:
    - Wiederhole NICHT den Titel am Anfang des Inhalts
    - Beginne den Inhalt direkt mit dem relevanten Text oder einer Einführung
    - Starte nicht mit einer Überschrift, die den Titel wiederholt
    - Stelle sicher, dass der Inhalt ohne den Titel vollständig verständlich ist

    Gib deine Antwort als JSON-Objekt mit folgenden Feldern zurück:
    - title: String mit dem neuen Titel
    - content: String mit dem überarbeiteten Inhalt in Markdown (ohne Wiederholung des Titels)
    - icon: String mit einem passenden Emoji
    """)

EXTRACT_REFERENCES_PROMPT = textwrap.dedent("""
    Analysiere folgenden Notion-Eintrag und finde die am besten passenden Projekte und Themen:

    TITEL: "{title}"
    INHALT:
    ---
    {content}
    ---

    VERFÜGBARE PROJEKTE:
    {projects}

    VERFÜGBARE THEMEN:
    {topics}

    WICHTIG:
    - Wähle NUR Projekte und Themen aus den verfügbaren Listen!
    - In den meisten Fällen passt nur 1 Projekt und 1 Thema am besten.
    - Wenn du dir nicht sicher bist, nenne lieber nichts als etwas Unpassendes.
    - Sei sehr präzise und wähle nur wirklich thematisch passende Einträge.
    - Bei Fachthemen ohne Projektbezug muss kein Projekt angegeben werden.

    Gib deine Antwort als JSON-Objekt mit folgenden Feldern zurück:
    - projects: Array von Strings mit 0-1 Projekten, die eindeutig passen
    - topics: Array von Strings mit 0-2 Themen, die eindeutig passen
    """)

assessment_parser = JsonOutputParser(pydantic_object=AssessmentResult)
revision_parser = JsonOutputParser(pydantic_object=RevisionResult)
references_parser = JsonOutputParser(pydantic_object=ReferencesResult)

# Erstelle Prompts mit Parsern
def create_structured_prompts(llm):
    """Erstellt strukturierte Prompts mit dem angegebenen LLM."""
    
    # Assessment Prompt mit JSON-Parser
    assessment_prompt_template = ChatPromptTemplate.from_template(ASSESSMENT_PROMPT)
    assessment_chain = assessment_prompt_template | llm | assessment_parser
    
    # Revision Prompts mit JSON-Parser
    revision_prompt_template = ChatPromptTemplate.from_template(REVISION_PROMPT)
    revision_chain = revision_prompt_template | llm | revision_parser
    
    revision_with_search_prompt_template = ChatPromptTemplate.from_template(REVISION_WITH_SEARCH_PROMPT)
    revision_with_search_chain = revision_with_search_prompt_template | llm | revision_parser
    
    # Extract References Prompt mit JSON-Parser
    extract_references_prompt_template = ChatPromptTemplate.from_template(EXTRACT_REFERENCES_PROMPT)
    extract_references_chain = extract_references_prompt_template | llm | references_parser
    
    return {
        "assessment": assessment_chain,
        "revision": revision_chain,
        "revision_with_search": revision_with_search_chain,
        "extract_references": extract_references_chain
    }

def get_revision_prompt(has_additional_info=False):
    """Gibt den Namen des passenden Revision-Prompts basierend auf dem Vorhandensein zusätzlicher Informationen zurück."""
    return "revision_with_search" if has_additional_info else "revision"