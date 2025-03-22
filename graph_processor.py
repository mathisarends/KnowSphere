# File: graph_processor.py
import logging
from typing import Dict, List, Any, Optional, TypedDict, Union
import os

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from notion.core.notion_page_manager import NotionPageManager

# Logging konfigurieren
logger = logging.getLogger("graph_processor")

# LLM Prompts
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

# State-Definition für den Graph
class State(TypedDict):
    messages: List[Any]
    current_draft: Optional[NotionPageManager]
    draft_content: Optional[Dict[str, Any]]
    needs_revision: bool
    revision_complete: bool
    stats: Dict[str, int]

class DraftLangGraph:
    """
    Implementiert einen LangGraph für die Verarbeitung von Notion-Entwürfen.
    """
    
    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.2):
        """
        Initialisiert den DraftLangGraph.
        
        Args:
            model_name: Name des OpenAI-Modells
            temperature: Temperature-Parameter für das LLM
        """
        api_key = os.environ.get("OPENAI_API_KEY", "sk-your-key-here")
        self.llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=temperature)
        
        # Graph-Komponenten initialisieren
        self.build_graph()
    
    def build_graph(self):
        """Erstellt den LangGraph für die Entwurfsverarbeitung."""
        # Graph initialisieren
        self.workflow = StateGraph(State)
        self.memory = MemorySaver()
        
        # Knoten hinzufügen
        self.workflow.add_node("get_content", self.get_content_node)
        self.workflow.add_node("assess_draft", self.assess_draft_node)
        self.workflow.add_node("revise_draft", self.revise_draft_node)
        self.workflow.add_node("update_stats", self.update_stats_node)
        
        # Einstiegspunkt definieren
        self.workflow.set_entry_point("get_content")
        
        # Bedingte Kanten
        self.workflow.add_conditional_edges(
            "get_content",
            self.route_after_content,
            {
                "assess_draft": "assess_draft",
                "update_stats": "update_stats",
                "end": END
            }
        )
        
        self.workflow.add_conditional_edges(
            "assess_draft",
            self.route_after_assessment,
            {
                "revise_draft": "revise_draft",
                "update_stats": "update_stats"
            }
        )
        
        self.workflow.add_conditional_edges(
            "revise_draft",
            lambda _: "update_stats",
            {
                "update_stats": "update_stats"
            }
        )
        
        self.workflow.add_conditional_edges(
            "update_stats",
            lambda _: "end",
            {
                "end": END
            }
        )
        
        # Graph kompilieren
        self.compiled_graph = self.workflow.compile(checkpointer=self.memory)
    
    async def get_content_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Ruft den Inhalt des aktuellen Entwurfs ab."""
        page_manager = state.get("current_draft")
        
        if not page_manager:
            logger.error("Kein aktueller Entwurf vorhanden")
            return {
                "messages": state.get("messages", []) + [
                    AIMessage(content="Fehler: Kein Entwurf angegeben.")
                ],
                "draft_content": None,
                "revision_complete": True
            }
        
        try:
            content = await page_manager.get_page_text()
            logger.info(f"Inhalt für '{page_manager.title}' erfolgreich abgerufen.")
            
            draft_content = {
                "title": page_manager.title,
                "content": content if content else "Kein Inhalt vorhanden.",
                "exists": True
            }
            
            return {
                "messages": state.get("messages", []) + [
                    HumanMessage(content=f"Entwurf: {page_manager.title}")
                ],
                "draft_content": draft_content
            }
            
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Inhalts: {e}")
            
            return {
                "messages": state.get("messages", []) + [
                    AIMessage(content=f"Fehler beim Abrufen des Inhalts: {str(e)}")
                ],
                "draft_content": None,
                "revision_complete": True
            }
    
    async def assess_draft_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Bewertet den Entwurf und entscheidet, ob eine Überarbeitung notwendig ist."""
        prompt = ChatPromptTemplate.from_template(ASSESSMENT_PROMPT)
        chain = prompt | self.llm
        
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
            updates["needs_revision"] = False
            updates["revision_complete"] = True
        
        return updates
    
    async def revise_draft_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Überarbeitet den Entwurf basierend auf dem LLM-Output."""
        prompt = ChatPromptTemplate.from_template(REVISION_PROMPT)
        chain = prompt | self.llm
        
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
        
        # Draft aktualisieren
        page_manager = state.get("current_draft")
        update_success = False
        update_message = ""
        
        try:
            original_title = page_manager.title
            result = await page_manager.update_page_content(
                new_title=new_title,
                new_content=new_content,
                icon_emoji=icon_emoji
            )
            
            logger.info(f"Entwurf '{original_title}' erfolgreich aktualisiert zu '{new_title}'")
            update_success = True
            update_message = f"Entwurf wurde aktualisiert: {new_title}"
            
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren des Entwurfs: {e}")
            update_message = f"Fehler beim Aktualisieren: {str(e)}"
        
        return {
            "messages": state.get("messages", []) + [
                revision,
                AIMessage(content=update_message)
            ],
            "revision_complete": True,
            "revision_successful": update_success
        }
    
    async def update_stats_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Aktualisiert die Statistiken des Durchlaufs."""
        stats = state.get("stats", {})
        current_total = stats.get("total", 0) + 1
        
        if not state.get("draft_content"):
            # Error beim Content-Abrufen
            current_errors = stats.get("errors", 0) + 1
            status = "error"
        elif state.get("needs_revision", False):
            if state.get("revision_successful", False):
                current_revised = stats.get("revised", 0) + 1
                status = "revised"
            else:
                current_errors = stats.get("errors", 0) + 1
                status = "revision_error"
        else:
            current_skipped = stats.get("skipped", 0) + 1
            status = "skipped"
        
        updated_stats = {
            "total": current_total,
            "revised": stats.get("revised", 0) + (1 if status == "revised" else 0),
            "skipped": stats.get("skipped", 0) + (1 if status == "skipped" else 0),
            "errors": stats.get("errors", 0) + (1 if "error" in status else 0)
        }
        
        # Titel für Logging
        title = ""
        if state.get("current_draft"):
            title = state.get("current_draft").title
        elif state.get("draft_content"):
            title = state.get("draft_content").get("title", "")
        
        logger.info(f"Entwurf abgeschlossen: '{title}' - Status: {status}")
        
        return {
            "stats": updated_stats,
            "revision_complete": True
        }
    
    def route_after_content(self, state: Dict[str, Any]) -> str:
        """Entscheidet, welcher Knoten nach dem Content-Abruf ausgeführt werden soll."""
        if not state.get("draft_content"):
            # Fehler beim Abrufen des Inhalts
            return "update_stats"
        return "assess_draft"
    
    def route_after_assessment(self, state: Dict[str, Any]) -> str:
        """Entscheidet, welcher Knoten nach der Bewertung ausgeführt werden soll."""
        if state.get("needs_revision", False):
            return "revise_draft"
        return "update_stats"
    
    async def process_draft(self, page_manager: NotionPageManager) -> Dict[str, Any]:
        """
        Verarbeitet einen einzelnen Entwurf mit dem LangGraph.
        
        Args:
            page_manager: Der NotionPageManager des Entwurfs
            
        Returns:
            Dict mit dem Endergebnis
        """
        # Anfangszustand definieren
        initial_state = {
            "messages": [],
            "current_draft": page_manager,
            "draft_content": None,
            "needs_revision": False,
            "revision_complete": False,
            "stats": {
                "total": 0,
                "revised": 0,
                "skipped": 0,
                "errors": 0
            }
        }
        
        # Graph ausführen
        try:
            config = {"thread_id": page_manager.page_id}
            final_state = await self.compiled_graph.ainvoke(initial_state, config=config)
            
            # Status ermitteln
            stats = final_state.get("stats", {})
            if stats.get("revised", 0) > 0:
                status = "revised"
            elif stats.get("skipped", 0) > 0:
                status = "skipped"
            else:
                status = "error"
            
            return {
                "success": status != "error",
                "status": status,
                "messages": final_state.get("messages", []),
                "stats": stats
            }
            
        except Exception as e:
            logger.error(f"Fehler bei der Ausführung des Graphs für Entwurf '{page_manager.title}': {e}")
            return {
                "success": False,
                "status": "graph_error",
                "error": str(e)
            }