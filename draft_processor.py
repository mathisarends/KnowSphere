# File: draft_processor.py
import logging
import os
from typing import Dict, Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from notion.core.notion_page_manager import NotionPageManager

# Logging konfigurieren
logger = logging.getLogger("draft_processor")

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

class DraftProcessor:
    """
    Klasse zum Verarbeiten einzelner Notion-Entwürfe mit LLM-basierten Ketten.
    """
    
    def __init__(self, model_name: str = "gpt-4o", temperature: float = 0.2):
        """
        Initialisiert den DraftProcessor mit einem LLM.
        
        Args:
            model_name: Name des OpenAI-Modells
            temperature: Temperature-Parameter für das LLM
        """
        api_key = os.environ.get("OPENAI_API_KEY", "sk-your-key-here")
        self.llm = ChatOpenAI(model=model_name, api_key=api_key, temperature=temperature)
        
        # Prompts initialisieren
        self.assessment_prompt = ChatPromptTemplate.from_template(ASSESSMENT_PROMPT)
        self.revision_prompt = ChatPromptTemplate.from_template(REVISION_PROMPT)
        
        # Chains erstellen
        self.assessment_chain = self.assessment_prompt | self.llm
        self.revision_chain = self.revision_prompt | self.llm

    async def get_draft_content(self, page_manager: NotionPageManager) -> Dict[str, Any]:
        """
        Ruft den Inhalt eines Entwurfs ab.
        
        Args:
            page_manager: Der NotionPageManager des Entwurfs
            
        Returns:
            Dict mit dem Inhalt oder Fehlermeldung
        """
        try:
            content = await page_manager.get_page_text()
            logger.info(f"Inhalt für '{page_manager.title}' erfolgreich abgerufen.")
            return {
                "title": page_manager.title,
                "content": content if content else "Kein Inhalt vorhanden.",
                "exists": True
            }
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Inhalts: {e}")
            return {
                "error": f"Fehler beim Abrufen des Inhalts: {e}",
                "exists": False
            }
    
    async def assess_draft(self, title: str, content: str) -> Dict[str, Any]:
        """
        Bewertet einen Entwurf und entscheidet, ob er überarbeitet werden sollte.
        
        Args:
            title: Titel des Entwurfs
            content: Inhalt des Entwurfs
            
        Returns:
            Dict mit Bewertungsergebnis und Entscheidung zur Überarbeitung
        """
        assessment = await self.assessment_chain.ainvoke({"title": title, "content": content})
        
        needs_revision = "ÜBERARBEITUNG NOTWENDIG: Ja" in assessment.content
        
        return {
            "assessment": assessment.content,
            "needs_revision": needs_revision
        }
    
    async def revise_draft(self, title: str, content: str) -> Dict[str, Any]:
        """
        Überarbeitet einen Entwurf.
        
        Args:
            title: Titel des Entwurfs
            content: Inhalt des Entwurfs
            
        Returns:
            Dict mit überarbeitetem Titel, Inhalt und Icon
        """
        revision = await self.revision_chain.ainvoke({"title": title, "content": content})
        revision_text = revision.content
        
        print("revision_text", revision_text)
        
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
        
        return {
            "new_title": new_title,
            "new_content": new_content,
            "icon_emoji": icon_emoji,
            "raw_revision": revision_text
        }
    
    async def update_draft(self, page_manager: NotionPageManager, 
                          new_title: str, new_content: str, icon_emoji: str = "🤖") -> Dict[str, Any]:
        """
        Aktualisiert einen Entwurf in Notion.
        
        Args:
            page_manager: Der NotionPageManager des Entwurfs
            new_title: Der neue Titel
            new_content: Der neue Inhalt
            icon_emoji: Das neue Icon-Emoji
            
        Returns:
            Dict mit dem Ergebnis der Aktualisierung
        """
        try:
            original_title = page_manager.title
            result = await page_manager.update_page_content(
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
    
    async def process_draft(self, page_manager: NotionPageManager) -> Dict[str, Any]:
        """
        Verarbeitet einen einzelnen Entwurf vollständig.
        
        Args:
            page_manager: Der NotionPageManager des Entwurfs
            
        Returns:
            Dict mit Ergebnis der Verarbeitung
        """
        logger.info(f"Verarbeite Entwurf: {page_manager.title}")
        
        # Inhalt abrufen
        content_result = await self.get_draft_content(page_manager)
        if not content_result.get("exists", False):
            return {
                "success": False,
                "status": "content_error",
                "message": f"Fehler beim Abrufen des Inhalts: {content_result.get('error')}"
            }
        
        title = content_result.get("title")
        content = content_result.get("content")
        
        # Entwurf bewerten
        assessment_result = await self.assess_draft(title, content)
        
        if not assessment_result.get("needs_revision"):
            logger.info(f"Entwurf '{title}' benötigt keine Überarbeitung.")
            return {
                "success": True,
                "status": "skipped",
                "message": f"Entwurf '{title}' benötigt keine Überarbeitung.",
                "assessment": assessment_result.get("assessment")
            }
        
        # Entwurf überarbeiten
        revision_result = await self.revise_draft(title, content)
        
        # Entwurf aktualisieren
        update_result = await self.update_draft(
            page_manager=page_manager,
            new_title=revision_result.get("new_title"),
            new_content=revision_result.get("new_content"),
            icon_emoji=revision_result.get("icon_emoji")
        )
        
        return {
            "success": update_result.get("success", False),
            "status": "revised" if update_result.get("success", False) else "update_error",
            "message": update_result.get("message", update_result.get("error", "Unbekannter Fehler")),
            "assessment": assessment_result.get("assessment"),
            "revision": revision_result.get("raw_revision")
        }