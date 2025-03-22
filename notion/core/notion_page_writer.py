from typing import Any, Dict, List, Optional
from notion.core.notion_abstract_client import AbstractNotionClient, HttpMethod
from notion.core.notion_content_converter import NotionContentConverter
from notion.core.notion_pages import NotionPages


class NotionPageWriter(AbstractNotionClient):
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
        """Fügt formatierten Text zur Seite hinzu, optional mit einem Trennzeichen.
        
        Args:
            text: Markdown-Text, der zur Seite hinzugefügt werden soll
            add_divider: Ob ein Trennzeichen vor dem Inhalt hinzugefügt werden soll
            
        Returns:
            Erfolgs- oder Fehlermeldung
        """
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
        """Ruft alle Inhalte von der Seite ab.
        
        Returns:
            Liste von Block-Objekten oder leere Liste bei Fehler
        """
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
        """Löscht alle Inhalte von der Seite.
        
        Returns:
            Erfolgs- oder Fehlermeldung
        """
        # Zuerst alle Blöcke auf der Seite abrufen
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
    
    async def delete_block(self, block_id: str) -> bool:
        """Löscht einen bestimmten Block von der Seite.
        
        Args:
            block_id: ID des zu löschenden Blocks
            
        Returns:
            True, wenn das Löschen erfolgreich war, sonst False
        """
        response = await self._make_request(
            HttpMethod.DELETE,
            f"blocks/{block_id}"
        )
        
        if "error" in response:
            self.logger.error("Fehler beim Löschen des Blocks %s: %s", block_id, response.get('error'))
            return False
        else:
            self.logger.info("Block %s erfolgreich gelöscht.", block_id)
            return True