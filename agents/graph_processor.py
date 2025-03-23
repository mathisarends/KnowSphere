from typing import Dict, List, Any, Optional, TypedDict
import os
from agents.prompts import ASSESSMENT_PROMPT, REVISION_PROMPT

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from notion.core.notion_page_manager import NotionPageManager
from util.logging_mixin import LoggingMixin

class State(TypedDict):
    messages: List[Any]
    page_id: str
    page_title: str
    draft_content: Optional[Dict[str, Any]]
    needs_revision: bool
    revision_complete: bool
    revision_successful: bool

class DraftLangGraph(LoggingMixin):
    """
    Implementiert einen LangGraph für die Verarbeitung von Notion-Entwürfen.
    """
    
    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.4):
        api_key = os.environ.get("OPENAI_API_KEY", "sk-your-key-here")
        self.llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=temperature)
        
        # Initialisiere current_page_manager mit None
        self.current_page_manager = None
        
        self.build_graph()
    
    def build_graph(self):
        self.workflow = StateGraph(State)
        self.memory = MemorySaver()

        # Knoten hinzufügen
        self.workflow.add_node("get_content", self.get_content_node)
        self.workflow.add_node("assess_draft", self.assess_draft_node)
        self.workflow.add_node("revise_draft", self.revise_draft_node)

        # Einstiegspunkt definieren
        self.workflow.set_entry_point("get_content")

        # Bedingte Kanten
        self.workflow.add_conditional_edges(
            "get_content",
            self.route_after_content,
            {
                "assess_draft": "assess_draft",
                "end": END
            }
        )

        self.workflow.add_conditional_edges(
            "assess_draft",
            self.route_after_assessment,
            {
                "revise_draft": "revise_draft",
                "end": END
            }
        )

        self.workflow.add_edge("revise_draft", END)

        # Graph kompilieren
        self.compiled_graph = self.workflow.compile(checkpointer=self.memory)
    
    async def get_content_node(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Ruft den Inhalt des aktuellen Entwurfs ab."""
        page_title = state.get("page_title", "Unbekannter Titel")
        
        if not self.current_page_manager:
            self.logger.error("Kein aktueller Entwurf vorhanden")
            return {
                "messages": state.get("messages", []) + [
                    AIMessage(content="Fehler: Kein Entwurf angegeben.")
                ],
                "draft_content": None,
                "revision_complete": True
            }
        
        try:
            content = await self.current_page_manager.get_page_text()
            self.logger.info("Inhalt für '%s' erfolgreich abgerufen.", page_title)
            
            draft_content = {
                "title": page_title,
                "content": content if content else "Kein Inhalt vorhanden.",
                "exists": True
            }
            
            return {
                "messages": state.get("messages", []) + [
                    HumanMessage(content=f"Entwurf: {page_title}")
                ],
                "draft_content": draft_content
            }
            
        except Exception as e:
            self.logger.error("Fehler beim Abrufen des Inhalts: %s", e)
            
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
            self.logger.info("Entwurf '%s' benötigt Überarbeitung.", title)
        else:
            self.logger.info("Entwurf '%s' benötigt keine Überarbeitung.", title)
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
        update_success = False
        update_message = ""
        
        try:
            # Verwende die externe NotionPageManager-Instanz statt der aus dem State
            original_title = self.current_page_manager.title
            result = await self.current_page_manager.update_page_content(
                new_title=new_title,
                new_content=new_content,
                icon_emoji=icon_emoji
            )
            
            self.logger.info("Entwurf '%s' erfolgreich aktualisiert zu '%s'", original_title, new_title)
            update_success = True
            update_message = f"Entwurf wurde aktualisiert: {new_title}"
            
        except Exception as e:
            self.logger.error("Fehler beim Aktualisieren des Entwurfs: %s", e)
            update_message = f"Fehler beim Aktualisieren: {str(e)}"
        
        return {
            "messages": state.get("messages", []) + [
                revision,
                AIMessage(content=update_message)
            ],
            "revision_complete": True,
            "revision_successful": update_success
        }
    
    def route_after_content(self, state: Dict[str, Any]) -> str:
        if not state.get("draft_content"):
            return "end"
        return "assess_draft"

    def route_after_assessment(self, state: Dict[str, Any]) -> str:
        if state.get("needs_revision", False):
            return "revise_draft"
        return "end"
        
    async def process_draft(self, page_manager: NotionPageManager) -> Dict[str, Any]:
        # Stelle page_manager außerhalb des States zur Verfügung
        self.current_page_manager = page_manager
        
        initial_state = {
            "messages": [],
            "page_id": page_manager.page_id,
            "page_title": page_manager.title,
            "draft_content": None,
            "needs_revision": False,
            "revision_complete": False,
            "revision_successful": False,
        }
        
        # Graph ausführen
        try:
            config = {"thread_id": page_manager.page_id}
            final_state = await self.compiled_graph.ainvoke(initial_state, config=config)
            
            # Status ermitteln
            if final_state.get("revision_successful", False):
                status = "revised"
            elif final_state.get("revision_complete", False) and not final_state.get("needs_revision", False):
                status = "skipped"
            else:
                status = "error"
            
            return {
                "success": status != "error",
                "status": status,
                "messages": final_state.get("messages", []),
            }
            
        except Exception as e:
            self.logger.error("Fehler bei der Ausführung des Graphs für Entwurf '%s': %s", page_manager.title, e)
            return {
                "success": False,
                "status": "graph_error",
                "error": str(e)
            }