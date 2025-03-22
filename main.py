import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple, TypedDict, Union
import os
from datetime import datetime

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver

from notion.core.notion_abstract_client import AbstractNotionClient
from notion.core.notion_page_manager import NotionPageManager
from notion.core.notion_pages import NotionPages
from notion.second_brain_manager import SecondBrainManager

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"draft_revision_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("draft_revision_agent")

# Konfiguration
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-your-key-here")
MODEL_NAME = "gpt-4o"
BATCH_SIZE = 5

# Globale Variablen für den State
sbm = None
drafts_generator = None
current_page_manager = None
processed_count = 0
total_count = 0

# LLM initialisieren
llm = ChatOpenAI(model=MODEL_NAME, api_key=OPENAI_API_KEY, temperature=0.2)

# Zustandsdefinition als Dictionary
class State(TypedDict):
    messages: List[Any]
    current_draft: Optional[Dict[str, Any]]
    draft_content: Optional[Dict[str, Any]]
    needs_revision: bool
    revision_complete: bool
    all_drafts_processed: bool

# DIRECT FUNCTION IMPLEMENTATIONS
# These functions are used directly in the workflow nodes

async def get_next_draft_impl() -> Dict[str, Any]:
    """
    Holt den nächsten Entwurf aus der Warteschlange.
    
    Returns:
        Dict mit Informationen zum nächsten Entwurf oder None, wenn keine weiteren Entwürfe vorhanden sind.
    """
    global current_page_manager, sbm, drafts_generator, processed_count
    
    try:
        current_page_manager = await drafts_generator.__anext__()
        processed_count += 1
        logger.info(f"Draft {processed_count} gefunden: {current_page_manager.title}")
        return {
            "id": current_page_manager.page_id,
            "title": current_page_manager.title,
            "url": current_page_manager.url,
            "exists": True
        }
    except StopAsyncIteration:
        logger.info("Keine weiteren Entwürfe vorhanden.")
        return {
            "exists": False,
            "message": "Keine weiteren Entwürfe vorhanden."
        }

async def get_draft_content_impl() -> Dict[str, Any]:
    """
    Ruft den Inhalt des aktuellen Entwurfs ab.
    
    Returns:
        Dict mit dem Inhalt des aktuellen Entwurfs.
    """
    global current_page_manager
    
    if not current_page_manager:
        return {"error": "Kein aktueller Entwurf vorhanden."}
    
    try:
        content = await current_page_manager.get_page_text()
        logger.info(f"Inhalt für '{current_page_manager.title}' erfolgreich abgerufen.")
        return {
            "title": current_page_manager.title,
            "content": content if content else "Kein Inhalt vorhanden.",
            "exists": True
        }
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des Inhalts: {e}")
        return {
            "error": f"Fehler beim Abrufen des Inhalts: {e}",
            "exists": False
        }

async def update_draft_impl(new_title: str, new_content: str, icon_emoji: str = "🤖") -> Dict[str, Any]:
    """
    Aktualisiert den aktuellen Entwurf mit neuem Titel und Inhalt.
    
    Args:
        new_title: Der neue Titel für den Entwurf
        new_content: Der neue Inhalt als Markdown-Text
        icon_emoji: Das Icon-Emoji für den Entwurf (Standard: 🤖)
        
    Returns:
        Dict mit dem Ergebnis der Aktualisierung
    """
    global current_page_manager
    
    if not current_page_manager:
        return {"error": "Kein aktueller Entwurf vorhanden."}
    
    try:
        original_title = current_page_manager.title
        result = await current_page_manager.update_page_content(
            new_title=new_title,
            new_content=new_content,
            icon_emoji=icon_emoji
        )
        
        logger.info(f"Entwurf '{original_title}' erfolgreich aktualisiert zu '{new_title}'")
        return {
            "success": True,
            "message": f"Entwurf erfolgreich aktualisiert.",
            "details": result
        }
    except Exception as e:
        logger.error(f"Fehler beim Aktualisieren des Entwurfs: {e}")
        return {
            "success": False,
            "error": f"Fehler beim Aktualisieren des Entwurfs: {e}"
        }

async def skip_draft_impl() -> Dict[str, Any]:
    """
    Überspringt den aktuellen Entwurf ohne Änderungen.
    
    Returns:
        Dict mit Bestätigung
    """
    global current_page_manager
    
    if not current_page_manager:
        return {"message": "Kein aktueller Entwurf zum Überspringen vorhanden."}
    
    title = current_page_manager.title
    logger.info(f"Entwurf '{title}' übersprungen.")
    return {
        "message": f"Entwurf '{title}' übersprungen."
    }

# TOOL DEFINITIONS (for LLM usage)
# These are separated from the workflow implementation

@tool
async def get_next_draft(tool_input: str = "") -> Dict[str, Any]:
    """
    Holt den nächsten Entwurf aus der Warteschlange.
    
    Returns:
        Dict mit Informationen zum nächsten Entwurf oder None, wenn keine weiteren Entwürfe vorhanden sind.
    """
    return await get_next_draft_impl()

@tool
async def get_draft_content(tool_input: str = "") -> Dict[str, Any]:
    """
    Ruft den Inhalt des aktuellen Entwurfs ab.
    
    Returns:
        Dict mit dem Inhalt des aktuellen Entwurfs.
    """
    return await get_draft_content_impl()

@tool
async def update_draft(tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Aktualisiert den aktuellen Entwurf mit neuem Titel und Inhalt.
    
    Args:
        tool_input: Dictionary mit new_title, new_content und optional icon_emoji
        
    Returns:
        Dict mit dem Ergebnis der Aktualisierung
    """
    new_title = tool_input.get("new_title", "")
    new_content = tool_input.get("new_content", "")
    icon_emoji = tool_input.get("icon_emoji", "🤖")
    return await update_draft_impl(new_title, new_content, icon_emoji)

@tool
async def skip_draft(tool_input: str = "") -> Dict[str, Any]:
    """
    Überspringt den aktuellen Entwurf ohne Änderungen.
    
    Returns:
        Dict mit Bestätigung
    """
    return await skip_draft_impl()

# Systemprompttemplates
ASSESSMENT_PROMPT = """
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
"""

REVISION_PROMPT = """
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
"""

# WORKFLOW NODE FUNCTIONS
# These use the direct implementation functions, not the tools

async def get_next_draft_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Holt den nächsten Entwurf und aktualisiert den State."""
    result = await get_next_draft_impl()  # Call the implementation directly
    
    updates = {
        "current_draft": result,
        "draft_content": None,
        "needs_revision": False,
        "revision_complete": False
    }
    
    if not result.get("exists", False):
        updates["all_drafts_processed"] = True
        updates["messages"] = state.get("messages", []) + [
            HumanMessage(content=f"Alle Entwürfe wurden verarbeitet. Insgesamt {processed_count} Entwürfe bearbeitet.")
        ]
    else:
        updates["messages"] = state.get("messages", []) + [
            HumanMessage(content=f"Neuer Entwurf gefunden: {result.get('title')}")
        ]
    
    return updates

async def get_content_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Ruft den Inhalt des aktuellen Entwurfs ab."""
    result = await get_draft_content_impl()  # Call the implementation directly
    
    updates = {
        "draft_content": result
    }
    
    if not result.get("exists", False):
        updates["messages"] = state.get("messages", []) + [
            HumanMessage(content=f"Fehler beim Abrufen des Inhalts: {result.get('error')}")
        ]
        updates["revision_complete"] = True
    
    return updates

async def assess_draft_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Bewertet den Entwurf und entscheidet, ob eine Überarbeitung notwendig ist."""
    prompt = ChatPromptTemplate.from_template(ASSESSMENT_PROMPT)
    chain = prompt | llm
    
    draft_content = state.get("draft_content", {})
    title = draft_content.get("title", "Unbekannter Titel")
    content = draft_content.get("content", "Kein Inhalt")
    
    assessment = await chain.ainvoke({"title": title, "content": content})
    
    updates = {
        "messages": state.get("messages", []) + [assessment]
    }
    
    # Prüfen, ob Überarbeitung notwendig ist
    if "ÜBERARBEITUNG NOTWENDIG: Ja" in assessment.content:
        updates["needs_revision"] = True
        logger.info(f"Entwurf '{title}' benötigt Überarbeitung.")
    else:
        logger.info(f"Entwurf '{title}' benötigt keine Überarbeitung.")
        await skip_draft_impl()  # Call the implementation directly
        updates["revision_complete"] = True
    
    return updates

async def revise_draft_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Überarbeitet den Entwurf basierend auf dem LLM-Output."""
    prompt = ChatPromptTemplate.from_template(REVISION_PROMPT)
    chain = prompt | llm
    
    draft_content = state.get("draft_content", {})
    title = draft_content.get("title", "Unbekannter Titel")
    content = draft_content.get("content", "Kein Inhalt")
    
    revision = await chain.ainvoke({"title": title, "content": content})
    
    # Extrahiere neuen Titel, Inhalt und Icon aus der Antwort
    revision_text = revision.content
    
    # Parsing der Revision
    new_title = title  # Standardwert, falls kein neuer Titel angegeben
    new_content = ""
    icon_emoji = "🤖"  # Standardwert
    
    # Titel extrahieren
    if "NEUER TITEL:" in revision_text:
        title_line = revision_text.split("NEUER TITEL:")[1].split("\n")[0].strip()
        if title_line:
            new_title = title_line
    
    # Inhalt extrahieren
    if "NEUER INHALT:" in revision_text:
        content_parts = revision_text.split("NEUER INHALT:")[1]
        if "ICON:" in content_parts:
            new_content = content_parts.split("ICON:")[0].strip()
        else:
            new_content = content_parts.strip()
    
    # Icon extrahieren
    if "ICON:" in revision_text:
        icon_line = revision_text.split("ICON:")[1].split("\n")[0].strip()
        if icon_line and len(icon_line) > 0:
            icon_emoji = icon_line
    
    # Draft aktualisieren (call the implementation directly)
    update_result = await update_draft_impl(
        new_title=new_title,
        new_content=new_content,
        icon_emoji=icon_emoji
    )
    
    return {
        "messages": state.get("messages", []) + [
            revision,
            AIMessage(content=f"Entwurf wurde aktualisiert:\nNeuer Titel: {new_title}\nIcon: {icon_emoji}")
        ],
        "revision_complete": True
    }

def should_process_next_draft(state: Dict[str, Any]) -> str:
    """Entscheidet, welcher Knoten als nächstes ausgeführt werden soll."""
    if state.get("all_drafts_processed", False):
        return "end"
    if state.get("current_draft") is None or state.get("revision_complete", False):
        return "get_next_draft"
    if state.get("draft_content") is None:
        return "get_content"
    if not state.get("needs_revision", False):
        return "assess_draft"
    else:
        return "revise_draft"

# Graph erstellen
def build_graph():
    # Erstelle einen leeren Zustand für den Einstiegspunkt
    workflow = StateGraph(State)
    memory = MemorySaver()
    
    # Knoten hinzufügen
    workflow.add_node("get_next_draft", get_next_draft_node)
    workflow.add_node("get_content", get_content_node)
    workflow.add_node("assess_draft", assess_draft_node)
    workflow.add_node("revise_draft", revise_draft_node)
    
    # Kanten definieren
    workflow.set_entry_point("get_next_draft")
    
    # Bedingte Kanten
    workflow.add_conditional_edges(
        "get_next_draft",
        should_process_next_draft,
        {
            "get_next_draft": "get_next_draft",
            "get_content": "get_content",
            "assess_draft": "assess_draft",
            "revise_draft": "revise_draft",
            "end": END
        }
    )
    
    workflow.add_conditional_edges(
        "get_content",
        should_process_next_draft,
        {
            "get_next_draft": "get_next_draft",
            "get_content": "get_content",
            "assess_draft": "assess_draft",
            "revise_draft": "revise_draft",
            "end": END
        }
    )
    
    workflow.add_conditional_edges(
        "assess_draft",
        should_process_next_draft,
        {
            "get_next_draft": "get_next_draft",
            "get_content": "get_content",
            "assess_draft": "assess_draft",
            "revise_draft": "revise_draft",
            "end": END
        }
    )
    
    workflow.add_conditional_edges(
        "revise_draft",
        should_process_next_draft,
        {
            "get_next_draft": "get_next_draft",
            "get_content": "get_content",
            "assess_draft": "assess_draft",
            "revise_draft": "revise_draft",
            "end": END
        }
    )
    
    return workflow.compile(checkpointer=memory)

# Hauptfunktion
async def run_draft_revision_agent():
    global sbm, drafts_generator, processed_count, total_count
    
    logger.info("Starte Draft Revision Agent...")
    
    # SecondBrainManager initialisieren
    sbm = SecondBrainManager()
    await sbm.__aenter__()
    
    try:
        # Generator für Pagination initialisieren
        drafts_generator = sbm.get_draft_entries_generator(batch_size=BATCH_SIZE)
        
        # Graph erstellen und ausführen
        graph = build_graph()
        initial_state = {
            "messages": [],
            "current_draft": None,
            "draft_content": None,
            "needs_revision": False,
            "revision_complete": False,
            "all_drafts_processed": False
        }
        
        # Stream-basierte Ausführung
        config = {"thread_id": "1"}  # Erhöhe, wenn nötig
        final_state = initial_state
        
        try:
            async for output_state in graph.astream(initial_state, config=config):
                final_state = output_state
                logger.info(f"Durchlauf durch Knoten, neuer Status: {final_state.keys()}")
        except Exception as e:
            logger.error(f"Fehler während der Graph-Ausführung: {e}", exc_info=True)
            raise
        
        logger.info(f"Draft Revision Agent abgeschlossen. {processed_count} Entwürfe verarbeitet.")
        
        # Nachrichten ausgeben (falls vorhanden)
        if "messages" in final_state and final_state["messages"]:
            messages_to_show = final_state["messages"][-5:] if len(final_state["messages"]) > 5 else final_state["messages"]
            for msg in messages_to_show:
                content = msg.content if hasattr(msg, "content") else str(msg)
                truncated = content[:100] + "..." if len(content) > 100 else content
                msg_type = getattr(msg, "type", "message")
                print(f"{msg_type}: {truncated}")
            
    except Exception as e:
        logger.error(f"Fehler bei der Ausführung des Draft Revision Agent: {e}", exc_info=True)
        raise
    finally:
        # Ressourcen freigeben
        await sbm.__aexit__(None, None, None)

if __name__ == "__main__":
    asyncio.run(run_draft_revision_agent())