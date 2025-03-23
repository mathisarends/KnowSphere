import asyncio
import json
from typing import AsyncGenerator, Dict, Any
import logging

from notion.core.notion_abstract_client import AbstractNotionClient, HttpMethod
from notion.core.notion_page_manager import NotionPageManager
from notion.core.notion_pages import NotionPages

class SecondBrainManager(AbstractNotionClient):
    def __init__(self):
        super().__init__()
        self.database_id = NotionPages.get_database_id("WISSEN_NOTIZEN")
    
    async def get_draft_entries_generator(self, batch_size: int = 10) -> AsyncGenerator[NotionPageManager, None]:
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
            
    # TODO: Kann eventuell auch noch in eine Datenbankbasierte Oberklasse:
    async def get_database_schema(self) -> Dict[str, Any]:
        """
        Ruft das Schema der Datenbank ab, um alle verfügbaren Eigenschaften zu sehen
        """
        response = await self._make_request(
            HttpMethod.GET,
            f"databases/{self.database_id}"
        )
        
        if response is None or "error" in response:
            error_msg = response.get('error', 'Unknown error') if response else 'No response'
            self.logger.error("Fehler beim Abrufen des Datenbankschemas: %s", error_msg)
            return {}
        
        # Extrahiere die Properties aus der Antwort
        properties = response.get("properties", {})
        return properties
    
async def main():
    # Konfiguriere Logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Erstelle eine Instanz des SecondBrainManager
    manager = SecondBrainManager()
    
    # Hole das Datenbankschema
    schema = await manager.get_database_schema()
    
    # Gib das Schema schön formatiert aus
    print("\n=== DATENBANKSCHEMA ===\n")
    
    for prop_name, prop_details in schema.items():
        prop_type = prop_details.get("type", "unknown")
        print(f"Eigenschaft: {prop_name}")
        print(f"Typ: {prop_type}")
        
        # Zeige zusätzliche Details je nach Eigenschaftstyp
        if prop_type == "select" and "select" in prop_details:
            options = prop_details["select"].get("options", [])
            print("Optionen:")
            for option in options:
                color = option.get("color", "default")
                name = option.get("name", "")
                print(f"  - {name} (Farbe: {color})")
        
        elif prop_type == "multi_select" and "multi_select" in prop_details:
            options = prop_details["multi_select"].get("options", [])
            print("Optionen:")
            for option in options:
                color = option.get("color", "default")
                name = option.get("name", "")
                print(f"  - {name} (Farbe: {color})")
        
        elif prop_type == "relation" and "relation" in prop_details:
            related_db = prop_details["relation"].get("database_id", "")
            print(f"  Verknüpft mit Datenbank: {related_db}")
        
        print("-" * 40)
    
    # Optional: Speichere das vollständige Schema in einer JSON-Datei für detailliertere Analyse
    with open("notion_schema.json", "w", encoding="utf-8") as f:
        json.dump(schema, f, ensure_ascii=False, indent=2)
    
    print(f"\nVollständiges Schema wurde in 'notion_schema.json' gespeichert.")

if __name__ == "__main__":
    asyncio.run(main())