from typing import AsyncGenerator
from notion.core.notion_abstract_client import AbstractNotionClient, HttpMethod
from notion.core.notion_page_manager import NotionPageManager
from notion.core.notion_pages import NotionPages
from notion.second_brain_page_manager import SecondBrainPageManager

class SecondBrainManager(AbstractNotionClient):
    def __init__(self):
        super().__init__()
        self.database_id = NotionPages.get_database_id("WISSEN_NOTIZEN")
    
    async def get_draft_entries_generator(self, batch_size: int = 10) -> AsyncGenerator[SecondBrainPageManager, None]:
        start_cursor = None
        has_more = True

        while has_more:
            filter_data = {
                "filter": {
                    "property": "Status",
                    "status": {
                        "equals": "Entwurf"
                    }
                },
                "page_size": batch_size
            }

            if start_cursor:
                filter_data["start_cursor"] = start_cursor

            response = await self._make_request(
                HttpMethod.POST,
                f"databases/{self.database_id}/query",
                filter_data
            )

            if response is None or "error" in response:
                error_msg = response.get('error', 'Unknown error') if response else 'No response'
                self.logger.error("Fehler beim Abfragen von Entwürfen: %s", error_msg)
                break

            results = response.get("results", [])
            start_cursor = response.get("next_cursor")
            has_more = response.get("has_more", False)

            for entry in results:
                page_id = entry.get("id")
                properties = entry.get("properties", {})

                # Extrahiere den Titel (Name)
                title = ""
                if "Name" in properties and "title" in properties["Name"]:
                    title_objects = properties["Name"]["title"]
                    if title_objects:
                        title = title_objects[0].get("text", {}).get("content", "")

                # Erstelle ein Page-Manager-Objekt für den Eintrag und gib es direkt zurück
                page_manager = NotionPageManager(page_id=page_id)
                
                # Setze Metadaten als Attribute, damit sie später verfügbar sind
                page_manager.title = title
                page_manager.url = entry.get("url", "")
                
                yield page_manager

            if not has_more:
                self.logger.info("Alle Entwürfe wurden abgerufen.")
                break     