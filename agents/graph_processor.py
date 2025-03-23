from typing import Dict, List, Any, Optional, TypedDict
import os

from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from notion.core.notion_page_manager import NotionPageManager
from notion.second_brain_page_manager import SecondBrainPageManager
from util.ai_response_utils import clean_markdown_code_blocks
from util.logging_mixin import LoggingMixin
from tools.tavily_search_tool import tavily_search

from agents.prompts import create_structured_prompts, get_revision_prompt

class SecondBrainDraftState(TypedDict):
    page_id: str
    page_title: str
    draft_content: Optional[Dict[str, Any]]
    needs_revision: bool
    revision_complete: bool
    revision_successful: bool
    requires_search: bool
    search_results: Optional[str]
    detected_tags: Optional[List[str]]
    detected_projects: Optional[List[str]]
    detected_topics: Optional[List[str]]
    available_projects: Optional[List[str]]
    available_topics: Optional[List[str]]

class DraftLangGraph(LoggingMixin):
    UNKNOWN_TITLE = "Unbekannter Titel"
    
    def __init__(self, model_name: str = "gpt-4o-mini", temperature: float = 0.4):
        api_key = os.environ.get("OPENAI_API_KEY", "sk-your-key-here")
        self.llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=temperature)
        
        self.prompts = create_structured_prompts(self.llm)
        
        self.current_page_manager = None
        
        self.build_graph()
    
    def build_graph(self):
        self.workflow = StateGraph(SecondBrainDraftState)
        self.memory = MemorySaver()

        # Knoten hinzufügen
        self.workflow.add_node("get_content", self.get_content_node)
        self.workflow.add_node("fetch_metadata", self.fetch_metadata_node)
        self.workflow.add_node("assess_draft", self.assess_draft_node)
        self.workflow.add_node("search_info", self.search_info_node)
        self.workflow.add_node("revise_draft", self.revise_draft_node)
        self.workflow.add_node("extract_references", self.extract_references_node)
        self.workflow.add_node("update_references", self.update_references_node)

        # Einstiegspunkt definieren
        self.workflow.set_entry_point("get_content")

        # Bedingte Kanten
        self.workflow.add_edge("get_content", "fetch_metadata")
        
        self.workflow.add_conditional_edges(
            "fetch_metadata",
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
                "search_info": "search_info",
                "revise_draft": "revise_draft",
                "extract_references": "extract_references",
                "end": END
            }
        )
        
        self.workflow.add_edge("search_info", "revise_draft")
        self.workflow.add_edge("revise_draft", "extract_references")
        self.workflow.add_edge("extract_references", "update_references")
        self.workflow.add_edge("update_references", END)

        self.compiled_graph = self.workflow.compile(checkpointer=self.memory)
    
    async def get_content_node(self, state: SecondBrainDraftState) -> SecondBrainDraftState:
        page_title = state.get("page_title", DraftLangGraph.UNKNOWN_TITLE)
        
        if not self.current_page_manager:
            self.logger.error("Kein aktueller Entwurf vorhanden")
            return {
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
                "draft_content": draft_content
            }
            
        except Exception as e:
            self.logger.error("Fehler beim Abrufen des Inhalts: %s", e)
            
            return {
                "draft_content": None,
                "revision_complete": True
            }
    
    async def fetch_metadata_node(self, state: SecondBrainDraftState) -> SecondBrainDraftState:
        """Ruft alle verfügbaren Projekte und Themen ab und speichert sie im State."""
        try:
            brain_manager = self._get_brain_manager()
            
            # Verfügbare Projekte und Themen abrufen
            available_projects = await brain_manager.get_all_project_names()
            available_topics = await brain_manager.get_all_topic_names()
            
            # Aktuelle Tags abrufen
            current_tags = await brain_manager.get_current_tags()
            
            self.logger.info("Metadata erfolgreich abgerufen: %d Projekte, %d Themen, %d Tags", 
                          len(available_projects), len(available_topics), len(current_tags))
            
            return {
                "available_projects": available_projects,
                "available_topics": available_topics,
                "detected_tags": current_tags,
                "detected_projects": [],
                "detected_topics": []
            }
            
        except Exception as e:
            self.logger.error("Fehler beim Abrufen der Metadata: %s", e)
            
            return {
                "available_projects": [],
                "available_topics": [],
                "detected_tags": [],
                "detected_projects": [],
                "detected_topics": []
            }
    
    async def assess_draft_node(self, state: SecondBrainDraftState) -> SecondBrainDraftState:
        """Bewertet den Entwurf und entscheidet, ob eine Überarbeitung notwendig ist."""
        draft_content = state.get("draft_content", {})
        title = draft_content.get("title", DraftLangGraph.UNKNOWN_TITLE)
        content = draft_content.get("content", "Kein Inhalt")
        
        try:
            # Verwende strukturierte Ausgabe
            assessment_result = await self.prompts["assessment"].ainvoke({"title": title, "content": content})
            
            if isinstance(assessment_result, dict):
                needs_revision = assessment_result.get("needs_revision", False)
                requires_search = assessment_result.get("requires_search", False)
                assessment_text = assessment_result.get("assessment", "Keine Bewertung verfügbar")
                reason = assessment_result.get("reason", "Kein Grund angegeben")
            else:
                needs_revision = assessment_result.needs_revision
                requires_search = assessment_result.requires_search
                assessment_text = assessment_result.assessment
                reason = assessment_result.reason
            
            assessment_message = f"""
                BEWERTUNG: {assessment_text}
                ÜBERARBEITUNG NOTWENDIG: {"Ja" if needs_revision else "Nein"}
                ZUSÄTZLICHE INFORMATIONEN NOTWENDIG: {"Ja" if requires_search else "Nein"}
                GRUND: {reason}
            """
            
            self.logger.info("Bewertung für '%s' abgeschlossen: Überarbeitung=%s, Recherche=%s\n%s", 
                          title, needs_revision, requires_search, assessment_message)
            
            return {
                "needs_revision": needs_revision,
                "requires_search": requires_search,
                "revision_complete": not needs_revision
            }
        except Exception as e:
            self.logger.error("Fehler bei der Bewertung des Entwurfs: %s", e)
            
            return {
                "needs_revision": False,
                "requires_search": False,
                "revision_complete": True
            }
    
    async def search_info_node(self, state: SecondBrainDraftState) -> SecondBrainDraftState:
        """Führt eine Websuche durch, um zusätzliche Informationen zu sammeln."""
        draft_content = state.get("draft_content", {})
        title = draft_content.get("title", "")
        
        try:
            search_results = tavily_search(
                query=title,
                max_results=2,
            )
            
            self.logger.info("Informationssuche für '%s' erfolgreich durchgeführt.", title)
            
            return {
                "search_results": search_results
            }
        except Exception as e:
            self.logger.error("Fehler bei der Informationssuche: %s", e)
            
            return {
                "search_results": None
            }
    
    async def revise_draft_node(self, state: SecondBrainDraftState) -> SecondBrainDraftState:
        """Überarbeitet den Entwurf basierend auf dem LLM-Output und Rechercheergebnissen."""
        draft_content = state.get("draft_content", {})
        title = draft_content.get("title", DraftLangGraph.UNKNOWN_TITLE)
        content = draft_content.get("content", "Kein Inhalt")
        
        has_additional_info = state.get("search_results") is not None
        prompt_name = get_revision_prompt(has_additional_info=has_additional_info)
        
        invoke_params = {"title": title, "content": content}
        
        if has_additional_info:
            invoke_params["additional_info"] = state.get("search_results")
        
        try:
            revision_result = await self.prompts[prompt_name].ainvoke(invoke_params)
            
            if isinstance(revision_result, dict):
                new_title = revision_result.get("title", title)
                new_content = clean_markdown_code_blocks(revision_result.get("content", content))
                icon_emoji = revision_result.get("icon", "🤖")
            else:
                # Zugriff auf Attribute des Objekts
                new_title = revision_result.title
                new_content = clean_markdown_code_blocks(revision_result.content)
                icon_emoji = revision_result.icon
            
            revision_summary = f"""
            NEUER TITEL: {new_title}
            NEUER INHALT:
            {new_content[:200]}... [gekürzt]
            ICON: {icon_emoji}
            """
            
            update_success = False
            
            try:
                original_title = self.current_page_manager.title
                await self.current_page_manager.update_page_content(
                    new_title=new_title,
                    new_content=new_content,
                    icon_emoji=icon_emoji
                )
                
                self.logger.info("Entwurf '%s' erfolgreich aktualisiert zu '%s'\n%s", 
                             original_title, new_title, revision_summary)
                update_success = True
                
                draft_content["title"] = new_title
                draft_content["content"] = new_content
                
            except Exception as e:
                self.logger.error("Fehler beim Aktualisieren des Entwurfs: %s", e)
            
            return {
                "revision_complete": True,
                "revision_successful": update_success,
                "draft_content": draft_content
            }
        except Exception as e:
            self.logger.error("Fehler bei der Überarbeitung: %s", e)
            
            return {
                "revision_complete": True,
                "revision_successful": False
            }
    
    async def extract_references_node(self, state: SecondBrainDraftState) -> SecondBrainDraftState:
        """Extrahiert Projekte und Themen aus dem überarbeiteten Inhalt."""
        draft_content = state.get("draft_content", {})
        title = draft_content.get("title", "")
        content = draft_content.get("content", "")
        
        available_projects = state.get("available_projects", [])
        available_topics = state.get("available_topics", [])
        
        current_tags = state.get("detected_tags", [])
        
        references_input = {
            "title": title,
            "content": content,
            "projects": ", ".join(available_projects),
            "topics": ", ".join(available_topics)
        }
        
        try:
            # Verwende strukturierte Ausgabe
            references_result = await self.prompts["extract_references"].ainvoke(references_input)
            
            if isinstance(references_result, dict):
                projects = references_result.get("projects", [])[:2]  # Begrenze auf max. 2 Projekte
                topics = references_result.get("topics", [])[:3]      # Begrenze auf max. 3 Themen
            else:
                # Zugriff auf Attribute des Objekts
                projects = references_result.projects[:2]  # Begrenze auf max. 2 Projekte
                topics = references_result.topics[:3]      # Begrenze auf max. 3 Themen
            
            self.logger.info("Extrahierte Referenzen: %d Projekte, %d Themen", 
                          len(projects), len(topics))
            
            return {
                "detected_tags": current_tags,
                "detected_projects": projects,
                "detected_topics": topics,
            }
            
        except Exception as e:
            self.logger.error("Fehler bei der Extraktion von Referenzen: %s", e)
            
            return {
                "detected_tags": current_tags,
                "detected_projects": [],
                "detected_topics": [],
            }
    
    async def update_references_node(self, state: SecondBrainDraftState) -> SecondBrainDraftState:
        """Aktualisiert die Referenzen (Tags, Projekte, Themen) in Notion."""
        tags = state.get("detected_tags", [])
        projects = state.get("detected_projects", [])
        topics = state.get("detected_topics", [])
        
        success_messages = []
        error_messages = []
        
        try:
            brain_manager = self._get_brain_manager()
            
            # Tags aktualisieren
            if tags:
                tags_success = await brain_manager.set_tags(tags)
                if tags_success:
                    success_messages.append(f"Tags aktualisiert: {', '.join(tags)}")
                else:
                    error_messages.append("Fehler beim Aktualisieren der Tags")
            
            # Projekte aktualisieren
            if projects:
                projects_success = await brain_manager.set_projects(projects)
                if projects_success:
                    success_messages.append(f"Projekte aktualisiert: {', '.join(projects)}")
                else:
                    error_messages.append("Fehler beim Aktualisieren der Projekte")
            
            # Themen aktualisieren
            if topics:
                topics_success = await brain_manager.set_topics(topics)
                if topics_success:
                    success_messages.append(f"Themen aktualisiert: {', '.join(topics)}")
                else:
                    error_messages.append("Fehler beim Aktualisieren der Themen")
            
            status_message = "\n".join(success_messages + error_messages)
            self.logger.info("Referenzen aktualisiert: %s", status_message)
            
            # Leeres Dictionary zurückgeben, da keine Statusänderungen nötig sind
            return {}
            
        except Exception as e:
            error_msg = f"Fehler beim Aktualisieren der Referenzen: {str(e)}"
            self.logger.error(error_msg)
            
            return {}
    
    def _get_brain_manager(self) -> SecondBrainPageManager:
        """
        Konvertiert den current_page_manager in einen SecondBrainManager, falls nötig.
        """
        if isinstance(self.current_page_manager, SecondBrainPageManager):
            return self.current_page_manager
        
        return SecondBrainPageManager(page_id=self.current_page_manager.page_id)
    
    def route_after_content(self, state: SecondBrainDraftState) -> str:
        if not state.get("draft_content"):
            return "end"
        return "assess_draft"

    def route_after_assessment(self, state: SecondBrainDraftState) -> str:
        if not state.get("needs_revision", False):
            return "extract_references"
        
        if state.get("requires_search", False):
            return "search_info"
        
        return "revise_draft"
        
    async def process_draft(self, page_manager: NotionPageManager) -> SecondBrainDraftState:
        self.current_page_manager = page_manager
        
        initial_state = {
            "page_id": page_manager.page_id,
            "page_title": page_manager.title,
            "draft_content": None,
            "needs_revision": False,
            "revision_complete": False,
            "revision_successful": False,
            "requires_search": False,
            "search_results": None,
            "detected_tags": [],
            "detected_projects": [],
            "detected_topics": [],
            "available_projects": [],
            "available_topics": []
        }
        
        # Graph ausführen
        try:
            config = {"thread_id": page_manager.page_id}
            final_state = await self.compiled_graph.ainvoke(initial_state, config=config)
            
            if final_state.get("revision_successful", False):
                status = "revised"
            elif final_state.get("revision_complete", False) and not final_state.get("needs_revision", False):
                status = "skipped"
            else:
                status = "error"
            
            return {
                "success": status != "error",
                "status": status,
                "references": {
                    "tags": final_state.get("detected_tags", []),
                    "projects": final_state.get("detected_projects", []),
                    "topics": final_state.get("detected_topics", [])
                }
            }
            
        except Exception as e:
            self.logger.error("Fehler bei der Ausführung des Graphs für Entwurf '%s': %s", page_manager.title, e)
            return {
                "success": False,
                "status": "graph_error",
                "error": str(e)
            }