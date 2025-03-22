import logging
import asyncio
from typing import AsyncGenerator

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
            
async def revise_drafts_example():
    """Beispiel zur Überarbeitung von Entwürfen mit der neuen Methode."""
    print("=== Second Brain Entwürfe Überarbeitungs-Beispiel ===")
    
    async with SecondBrainManager() as sbm:
        # Generator für alle Entwürfe
        drafts_generator = sbm.get_draft_entries_generator(batch_size=5)
        
        # Ersten Entwurf als Beispiel nehmen
        try:
            page_manager = await drafts_generator.__anext__()
            
            print(f"Originaler Entwurf gefunden:")
            print(f"Titel: {page_manager.title}")
            print(f"ID: {page_manager.page_id}")
            
            # Aktuellen Inhalt anzeigen
            original_content = await page_manager.get_page_text()
            print("\n=== Originaler Inhalt ===")
            print(original_content if original_content else "Kein Inhalt vorhanden.")
            
            # Beispielhafte Überarbeitung
            new_title = f"[Überarbeitet] {page_manager.title}"
            new_content = """# Überarbeiteter Entwurf

Dies ist ein überarbeiteter Entwurf, der mit der neuen `revise_draft`-Methode erstellt wurde.

## Inhaltsüberarbeitung
- Der Originalinhalt wurde komplett ersetzt
- Der Titel wurde aktualisiert
- Der Status wurde auf "KI-Draft" geändert

## Vorteile
- Einfache API
- Alle Änderungen in einem Schritt
- Automatische Statusänderung
"""
            
            # Bestätigung vom Benutzer holen
            print("\n=== Überarbeitungsvorschau ===")
            print(f"Neuer Titel: {new_title}")
            print("\nNeuer Inhalt:")
            print(new_content)
            
            confirm = input("\nMöchten Sie den Entwurf wirklich überarbeiten? (j/n): ")
            
            if confirm.lower() == "j":
                # Überarbeitung durchführen
                result = await page_manager.update_page_content(
                    new_title=new_title,
                    new_content=new_content,
                    icon_emoji="✨"
                )
                
                print("\n=== Überarbeitungsergebnis ===")
                print(result)
                
                # Aktuellen Zustand nach Überarbeitung anzeigen
                updated_content = await page_manager.get_page_text()
                print("\n=== Aktualisierter Inhalt ===")
                print(updated_content if updated_content else "Kein Inhalt vorhanden.")
            else:
                print("Überarbeitung abgebrochen.")
                
        except StopAsyncIteration:
            print("Keine Entwürfe gefunden.")

if __name__ == "__main__":
    # Event-Loop ausführen
    asyncio.run(revise_drafts_example())            



# if __name__ == "__main__":
#     # Logging konfigurieren
#     logging.basicConfig(
#         level=logging.INFO,
#         format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
#     )
    
#     async def interact_with_drafts():
#         """Interaktive Konsolenanwendung zum Durchgehen der Entwürfe."""
#         print("=== Second Brain Entwürfe Viewer ===")
#         print("Durchsuche Entwürfe... (ENTER drücken, um weiterzugehen, 'q' zum Beenden)")
        
#         # Haupt-Session für die Datenbankabfragen
#         async with SecondBrainManager() as sbm:
#             # Generator für Pagination
#             drafts_generator = sbm.get_draft_entries_generator()
            
#             idx = 1
#             async for page_manager in drafts_generator:
#                 print(f"\n--- Entwurf {idx} ---")
#                 print(f"Titel: {page_manager.title}")
#                 print(f"ID: {page_manager.page_id}")
#                 print(f"URL: {page_manager.url}")
                
#                 action = input("\nOptionen: [ENTER] Weiter | [i] Inhalt anzeigen | [q] Beenden: ").lower()
                
#                 if action == 'q':
#                     print("Programm wird beendet.")
#                     break
#                 elif action == 'i':
#                     try:
#                         print("\n=== Seiteninhalt ===")
                        
#                         # Page-Text direkt vom PageManager abrufen
#                         page_text = await page_manager.get_page_text()
                        
#                         if not page_text or page_text == "Keine Inhalte gefunden.":
#                             print("Kein Inhalt gefunden oder Fehler beim Abrufen des Inhalts.")
#                         else:
#                             # Text mit korrekter Formatierung anzeigen
#                             print(page_text)
                        
#                         # Warten auf User-Input, um fortzufahren
#                         input("\nDrücke ENTER, um fortzufahren...")
#                     except Exception as e:
#                         print(f"Fehler beim Anzeigen des Inhalts: {e}")
#                         input("\nDrücke ENTER, um fortzufahren...")
                
#                 idx += 1
            
#             print("\nKeine weiteren Entwürfe gefunden oder Ende erreicht.")
    
#     # Event-Loop ausführen
#     asyncio.run(interact_with_drafts())
    
    