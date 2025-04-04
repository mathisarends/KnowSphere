import asyncio
from typing import Any, AsyncGenerator, Dict, Optional, Type
from notion.core.notion_abstract_client import AbstractNotionClient, HttpMethod
from notion.core.notion_page_manager import NotionPageManager
from notion.snipd_page_manager import SnipdPageManager

class NotionDatabaseManager(AbstractNotionClient):
    def __init__(self, database_id, token=None, timeout=30):
        super().__init__(token, timeout)
        self.database_id = database_id
        
    async def get_entries_generator(
            self, 
            filter_dict: Optional[Dict[str, Any]] = None, 
            batch_size: int = 10,
            page_manager_class: Type[NotionPageManager] = NotionPageManager  # Add this parameter
        ) -> AsyncGenerator[NotionPageManager, None]:
            """
            Get entries from the database with a generic filter.
            """
            start_cursor = None
            has_more = True

            while has_more:
                query_data = {"page_size": batch_size}
                
                # Add filter if provided
                if filter_dict:
                    query_data["filter"] = filter_dict
                    
                if start_cursor:
                    query_data["start_cursor"] = start_cursor

                response = await self._make_request(
                    HttpMethod.POST,
                    f"databases/{self.database_id}/query",
                    query_data
                )

                results = response.get("results", [])
                start_cursor = response.get("next_cursor")
                has_more = response.get("has_more", False)

                for entry in results:
                    page_id = entry.get("id")
                    properties = entry.get("properties", {})

                    # Extract title (Name)
                    title = ""
                    if "Name" in properties and "title" in properties["Name"]:
                        title_objects = properties["Name"]["title"]
                        if title_objects:
                            title = title_objects[0].get("text", {}).get("content", "")
                    
                    # For Episode title (specific to podcast episodes)
                    if not title and "Episode" in properties and "title" in properties["Episode"]:
                        title_objects = properties["Episode"]["title"]
                        if title_objects:
                            title = title_objects[0].get("text", {}).get("content", "")

                    # Create page manager object using the specified class
                    page_manager = page_manager_class(page_id=page_id)
                    
                    # Set metadata as attributes
                    page_manager.title = title
                    page_manager.url = entry.get("url", "")
                    
                    yield page_manager

                if not has_more:
                    self.logger.info("All matching entries have been retrieved.")
                    break
                
    
    async def get_database_schema(self):
        """Get the database schema (properties and structure)"""
        database = await self._make_request(HttpMethod.GET, f"databases/{self.database_id}")
        return database.get("properties", {})

async def demo():
    db = NotionDatabaseManager("1af389d5-7bd3-815c-937a-e0e39eb6343a")
    schema = await db.get_database_schema()
    print("Database schema:")
    print(schema)    

    filter_dict = {
         "property": "Status",
        "status": {
            "equals": "Nicht begonnen"
        }
    }
    
    print("\nEntries with Status = 'Nicht begonnen':")
    async for entry in db.get_entries_generator(filter_dict, page_manager_class=SnipdPageManager):
        print(f"- {entry.title} ({entry.url})")
        
        episode_show_notes = await entry.get_episode_show_notes()
        print(episode_show_notes)
        transcript = await entry.get_combined_transcripts()
        print(transcript)
        input("Press Enter to continue...")
        
        # Das hier können wir beides eigentlich gut in ein LLM werfen und dann gucken was er daraus macht:
    
    # Return a value instead of yielding
    return "Demo completed"

if __name__ == "__main__":
    asyncio.run(demo())