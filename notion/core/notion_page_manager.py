from typing import Any, Dict, List, Optional, Tuple
from notion.core.notion_abstract_client import AbstractNotionClient, HttpMethod
from notion.core.notion_content_converter import NotionContentConverter
from notion.core.notion_pages import NotionPages

class NotionPageManager(AbstractNotionClient):
    """Generische Klasse zum Schreiben und Verwalten von Notion-Seiten."""
    
    def __init__(self, page_id: str = None, page_name: str = None, token: Optional[str] = None):
        """Initialisiert den NotionPageWriter.
        
        Args:
            page_id: ID der Notion-Seite (direkt)
            page_name: Name der Notion-Seite (wird über NotionPages aufgelöst)
            token: Notion API Token
        """
        super().__init__(token=token)
        
        if page_id:
            self.page_id = page_id
        elif page_name:
            self.page_id = NotionPages.get_page_id(page_name)
        else:
            raise ValueError("Entweder page_id oder page_name muss angegeben werden")
    
    async def append_content(self, text: str, add_divider: bool = False) -> str:
        content_blocks = NotionContentConverter.markdown_to_blocks(text)
        
        if add_divider:
            divider_block = {
                "type": "divider",
                "divider": {}
            }
            content_blocks = [divider_block] + content_blocks
        
        data = {
            "children": content_blocks
        }
        
        response = await self._make_request(
            HttpMethod.PATCH, 
            f"blocks/{self.page_id}/children", 
            data
        )
        
        if "error" in response:
            self.logger.error("Fehler beim Hinzufügen von Text: %s", response.get('error'))
            return f"Fehler beim Hinzufügen von Text: {response.get('error')}"
        else:
            self.logger.info("Text erfolgreich zur Seite hinzugefügt.")
            return "Text erfolgreich zur Seite hinzugefügt."
    
    async def get_page_content(self) -> List[Dict[str, Any]]:
        response = await self._make_request(
            HttpMethod.GET, 
            f"blocks/{self.page_id}/children"
        )
        
        if "error" in response:
            self.logger.error("Fehler beim Abrufen des Seiteninhalts: %s", response.get('error'))
            return []
        
        return response.get("results", [])
    
    async def get_page_text(self) -> str:
        """Ruft den Seiteninhalt ab und konvertiert ihn in lesbaren Text.
        
        Returns:
            Textdarstellung des Seiteninhalts oder Fehlermeldung
        """
        blocks = await self.get_page_content()
        return NotionContentConverter.blocks_to_text(blocks)
    
    async def clear_page(self) -> str:
        blocks = await self.get_page_content()
        
        if not blocks:
            return "Keine Inhalte zum Löschen vorhanden oder Fehler beim Abrufen des Inhalts."
        
        # Jeden Block einzeln löschen
        deleted_count = 0
        for block in blocks:
            block_id = block.get("id")
            if not block_id:
                continue
                
            response = await self._make_request(
                HttpMethod.DELETE,
                f"blocks/{block_id}"
            )
            
            if "error" not in response:
                deleted_count += 1
        
        if deleted_count == len(blocks):
            self.logger.info("Alle %d Blöcke erfolgreich von der Seite gelöscht.", deleted_count)
            return f"Alle {deleted_count} Blöcke erfolgreich von der Seite gelöscht."
        else:
            self.logger.warning("Seite teilweise geleert. %d von %d Blöcken gelöscht.", deleted_count, len(blocks))
            return f"Seite teilweise geleert. {deleted_count} von {len(blocks)} Blöcken gelöscht."
    
    async def update_page_content(self, new_title: str = None, new_content: str = None, icon_emoji: str = "🤖") -> str:
        """Aktualisiert den Inhalt einer Notion-Seite inkl. Titel, Inhalt, Status und Icon.
        
        Args:
            new_title: Neuer Titel für die Seite (optional)
            new_content: Neuer Inhalt als Markdown-Text (optional)
            icon_emoji: Emoji-Icon für die Seite (Standard: Roboter-Emoji)
            
        Returns:
            Statusmeldung über den Erfolg der Aktualisierung
        """
        results = []
        
        # Titel und Icon in einem Request aktualisieren
        update_data = {
            "properties": {},
            "icon": {
                "type": "emoji",
                "emoji": icon_emoji
            }
        }
        
        # Titel hinzufügen, falls angegeben
        if new_title:
            update_data["properties"]["Name"] = {
                "title": [
                    {
                        "text": {
                            "content": new_title
                        }
                    }
                ]
            }
        
        # Status auf "KI-Draft" setzen
        update_data["properties"]["Status"] = {
            "status": {
                "name": "KI-Draft"
            }
        }
        
        # Page aktualisieren (Titel, Icon und Status in einem Request)
        update_response = await self._make_request(
            HttpMethod.PATCH,
            f"pages/{self.page_id}",
            update_data
        )
        
        if "error" in update_response:
            error_msg = f"Fehler bei der Aktualisierung der Seite: {update_response.get('error')}"
            self.logger.error(error_msg)
            results.append(error_msg)
        else:
            if new_title:
                self.logger.info("Titel erfolgreich aktualisiert: %s", new_title)
                results.append(f"Titel erfolgreich aktualisiert: {new_title}")
                # Attribute aktualisieren falls vorhanden
                if hasattr(self, 'title'):
                    self.title = new_title
                    
            self.logger.info("Icon erfolgreich auf %s gesetzt.", icon_emoji)
            results.append(f"Icon erfolgreich auf {icon_emoji} gesetzt.")
            
            self.logger.info("Status erfolgreich auf 'KI-Draft' gesetzt.")
            results.append("Status erfolgreich auf 'KI-Draft' gesetzt.")
        
        # Inhalt aktualisieren, falls angegeben
        if new_content:
            clear_result = await self.clear_page()
            results.append(clear_result)
            
            append_result = await self.append_content(new_content)
            results.append(append_result)
        
        return "\n".join(results)
