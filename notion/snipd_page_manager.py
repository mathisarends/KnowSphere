from typing import Any, Dict, List, Optional
from notion.core.notion_page_manager import NotionPageManager
from util.web_scraper import AsyncWebScraper

class SnipdPageManager(NotionPageManager):
    """
    Manager für Notion-Seiten mit Snipd-Links, der Transkripte extrahieren kann.
    """
    def __init__(self, page_id: str = None, page_name: str = None, token: Optional[str] = None):
        super().__init__(page_id=page_id, page_name=page_name, token=token)
        
    # TODO: Das hier muss zusammengelegt werden um eine Zusammenfassung des Poadcasts zu erstellen:
    async def get_episode_show_notes(self) -> str:
        """
        Extrahiert die Show Notes der Episode aus einer Notion-Seite.
        Sucht nach einem Toggle-Block mit dem Titel "Episode show notes" und extrahiert dessen Inhalt.
        """
        blocks = await self.get_page_content()
        
        # Suche nach dem Toggle-Block "Episode show notes"
        show_notes_toggle = None
        toggle_index = -1
        
        for i, block in enumerate(blocks):
            if block.get("type") == "toggle":
                toggle_content = block.get("toggle", {})
                rich_text = toggle_content.get("rich_text", [])
                
                toggle_text = ""
                for text_obj in rich_text:
                    if text_obj.get("type") == "text":
                        toggle_text += text_obj.get("text", {}).get("content", "")
                
                if "episode show notes" in toggle_text.lower():
                    show_notes_toggle = block
                    toggle_index = i
                    break
        
        if not show_notes_toggle:
            return "Keine Episode Show Notes gefunden."
        
        toggle_id = show_notes_toggle.get("id")
        if not toggle_id:
            return "Toggle-Block-ID konnte nicht gefunden werden."
        
        # Hole die Kinder-Blocks des Toggle-Blocks
        children_blocks = await self._get_block_children(toggle_id)
        
        if not children_blocks:
            return "Keine Inhalte in den Show Notes gefunden."
        
        show_notes_content = []
        for block in children_blocks:
            block_text = self._extract_block_text(block)
            if block_text:
                show_notes_content.append(block_text)
        
        if not show_notes_content:
            return "Keine Inhalte in den Show Notes gefunden."
        
        return "\n\n".join(show_notes_content)
    
    async def _get_block_children(self, block_id: str) -> List[Dict[str, Any]]:
        """
        Holt die Kinder-Blocks eines bestimmten Blocks.
        """
        from notion.core.notion_abstract_client import HttpMethod
        
        response = await self._make_request(
            HttpMethod.GET, 
            f"blocks/{block_id}/children"
        )
        
        if "error" in response:
            self.logger.error("Fehler beim Abrufen der Block-Kinder: %s", response.get('error'))
            return []
        
        return response.get("results", [])
    
    def _extract_block_text(self, block: Dict[str, Any]) -> str:
        """
        Extrahiert den Textinhalt aus einem Notion-Block.
        """
        block_type = block.get("type", "")
        
        if block_type in ["paragraph", "heading_1", "heading_2", "heading_3", "bulleted_list_item", "numbered_list_item"]:
            rich_text = block.get(block_type, {}).get("rich_text", [])
            return "".join([
                text_obj.get("text", {}).get("content", "")
                for text_obj in rich_text
                if text_obj.get("type") == "text"
            ])
        
        return ""
    
    async def get_combined_transcripts(self) -> str:
        """
        Extrahiert alle Snipd-Links von der Notion-Seite, scrapt deren Transkripte
        und gibt sie als einen kombinierten Text zurück.
        """
        links = await self._get_snipd_links()
        
        if not links:
            return "Keine Snipd-Links gefunden."
        
        combined_text = []
        
        for i, link in enumerate(links, 1):
            transcript = await self._scrape_snipd_url(link)
            
            if transcript:
                combined_text.append(f"Transcript {i}: {transcript}")
            else:
                combined_text.append(f"Transcript {i}: Kein Transkript gefunden für {link}")
        
        # Verbinde alle Transkripte mit Leerzeilen dazwischen
        return "\n\n".join(combined_text)
    
    # Alle weiteren Methoden sind privat (mit _ präfix)
    
    async def _get_snipd_links(self) -> List[str]:
        """
        Extrahiert alle Snipd-Links aus dem Seiteninhalt.
        """
        page_content = await self.get_page_content()
        links = []
        
        for block in page_content:
            # Prüfe, ob es sich um einen heading_3-Block handelt (wo Snips gespeichert sind)
            if block.get("type") == "heading_3":
                heading_data = block.get("heading_3", {})
                rich_text = heading_data.get("rich_text", [])
                
                if rich_text:
                    link = self._extract_link_from_rich_text(rich_text)
                    
                    if link:
                        links.append(link)
        
        return links
    
    def _extract_link_from_rich_text(self, rich_text) -> Optional[str]:
        """
        Extrahiert Links aus rich_text-Array eines Headings.
        """
        # Das erste Segment enthält typischerweise den Link
        if rich_text and len(rich_text) > 0:
            first_segment = rich_text[0]
            if first_segment.get("type") == "text":
                # Extrahiere Link, falls vorhanden
                link_data = first_segment.get("text", {}).get("link", {})
                if link_data:
                    url = link_data.get("url", "")
                    if "snipd.com" in url:
                        return url
        
        return None
    
    async def _scrape_snipd_url(self, url: str) -> Optional[str]:
        """
        Hilfsfunktion zum Scrapen eines einzelnen Snipd-Links
        """
        try:
            self.logger.info(f"Scraping URL: {url}")
            scraper = await AsyncWebScraper.from_url(url)
            transcript = await scraper.extract()
            
            if transcript:
                self.logger.info(f"Transkript gefunden ({len(transcript)} Zeichen)")
            else:
                self.logger.info("Kein Transkript gefunden")
            
            return transcript
        except Exception as e:
            self.logger.error(f"Fehler beim Scrapen von {url}: {str(e)}")
            return None