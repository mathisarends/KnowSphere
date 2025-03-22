import logging
from typing import List, Dict, Any

from notion.core.notion_abstract_client import AbstractNotionClient, HttpMethod
from notion.core.notion_pages import NotionPages

class SecondBrainManager(AbstractNotionClient):
    def __init__(self):
        super().__init__()
        self.database_id = NotionPages.get_database_id("WISSEN_NOTIZEN")
        
    async def get_draft_entries(self) -> List[Dict[str, Any]]:
        filter_data = {
            "filter": {
                "property": "Status",
                "status": {
                    "equals": "Entwurf"
                }
            }
        }
        
        try:
            response = await self._make_request(
                HttpMethod.POST, 
                f"databases/{self.database_id}/query", 
                filter_data
            )
            
            if response is None:
                self.logger.error("Keine Antwort vom Server beim Abfragen von Entwürfen.")
                return []
                
            if "error" in response:
                self.logger.error("Fehler beim Abfragen von Entwürfen: %s", response['error'])
                return []
            
            results = response.get("results", [])
            self.logger.info("%d Entwürfe gefunden.", len(results))
            
            draft_entries = []
            for entry in results:
                page_id = entry.get("id")
                properties = entry.get("properties", {})
                
                # Extrahiere den Titel (Name)
                title = ""
                if "Name" in properties and "title" in properties["Name"]:
                    title_objects = properties["Name"]["title"]
                    if title_objects:
                        title = title_objects[0].get("text", {}).get("content", "")
                
                draft_entries.append({
                    "id": page_id,
                    "title": title,
                    "url": entry.get("url", "")
                })
            
            return draft_entries
                
        except Exception as e:
            self.logger.error("❌ Fehler beim Abfragen von Entwürfen: %s", str(e))
            return []


if __name__ == "__main__":
    import asyncio
    
    async def main():
        # Mit Kontext-Manager ausführen, um sicherzustellen, dass die Session geschlossen wird
        async with SecondBrainManager() as second_brain_manager:
            # Alle Entwürfe abrufen
            drafts = await second_brain_manager.get_draft_entries()
            
            if drafts:
                print(f"Gefundene Entwürfe ({len(drafts)}):")
                for i, draft in enumerate(drafts, 1):
                    print(f"{i}. {draft['title']} (ID: {draft['id']})")
            else:
                print("Keine Entwürfe gefunden.")
    
    # Event-Loop ausführen
    asyncio.run(main())