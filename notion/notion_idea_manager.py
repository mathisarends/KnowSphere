from typing import List, Dict, Any, Optional
import asyncio

from notion.core.notion_abstract_client import AbstractNotionClient, HttpMethod
from notion.core.notion_pages import NotionPages


class NotionIdeaManager(AbstractNotionClient):
    def __init__(self, token: Optional[str] = None):
        super().__init__(token=token)
        self.database_id = NotionPages.get_database_id("IDEAS")
    
    async def add_idea(self, name: str, tags: Optional[List[str]] = None, status: str = "Initial") -> str:
        """Add a new idea to the Notion database.
        
        Args:
            name: The name of the idea
            tags: Optional list of tags for categorization
            status: The initial status of the idea
            
        Returns:
            Success or error message
        """
        data = {
            "parent": {"database_id": self.database_id},
            "properties": {
                "Name": {
                    "title": [{"text": {"content": name}}]
                },
                "Status": {
                    "status": {"name": status}
                }
            },
            "icon": {
                "type": "external",
                "external": {"url": "https://www.notion.so/icons/document_emoji_orange.svg"}
            }
        }

        # Add tags if provided
        if tags:
            data["properties"]["Art"] = {
                "multi_select": [{"name": tag} for tag in tags]
            }

        response = await self._make_request(HttpMethod.POST, "pages", data)

        if "error" in response:
            self.logger.error("❌ Error adding idea: %s", response['error'])
            return f"❌ Error adding idea: {response['error']}"
        else:
            self.logger.info("✅ Successfully added idea: %s", name)
            return f"✅ Idea '{name}' added successfully."

    async def get_all_ideas(self) -> List[Dict[str, Any]]:
        """Retrieve all ideas from the Notion database.
        
        Returns:
            List of ideas with their properties or error message
        """
        response = await self._make_request(HttpMethod.POST, f"databases/{self.database_id}/query")

        if "error" in response:
            self.logger.error("❌ Error retrieving ideas: %s", response['error'])
            return []

        try:
            results = response.get("results", [])
            ideas = []
            
            for item in results:
                # Handle potential missing values or structure differences safely
                idea = {"id": item["id"]}
                
                # Extract name
                title_items = item.get("properties", {}).get("Name", {}).get("title", [])
                idea["name"] = title_items[0]["text"]["content"] if title_items else "Unnamed"
                
                # Extract status
                status_obj = item.get("properties", {}).get("Status", {}).get("status", {})
                idea["status"] = status_obj.get("name", "No Status") if status_obj else "No Status"
                
                # Extract tags
                multi_select = item.get("properties", {}).get("Art", {}).get("multi_select", [])
                idea["tags"] = [tag.get("name", "") for tag in multi_select if tag.get("name")]
                
                ideas.append(idea)
                
            return ideas
            
        except Exception as e:
            self.logger.error(f"❌ Error parsing response: {str(e)}")
            return []

    async def update_idea(self, idea_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing idea.
        
        Args:
            idea_id: The ID of the idea to update
            updates: Dictionary with fields to update (name, status, tags)
            
        Returns:
            Success status
        """
        data = {"properties": {}}
        
        if "name" in updates:
            data["properties"]["Name"] = {
                "title": [{"text": {"content": updates["name"]}}]
            }
            
        if "status" in updates:
            data["properties"]["Status"] = {
                "status": {"name": updates["status"]}
            }
            
        if "tags" in updates:
            data["properties"]["Art"] = {
                "multi_select": [{"name": tag} for tag in updates["tags"]]
            }
            
        if "icon" in updates:
            data["icon"] = {
                "type": "external",
                "external": {"url": updates["icon"]}
            }
            
        response = await self._make_request(HttpMethod.PATCH, f"pages/{idea_id}", data)
        
        if "error" in response:
            self.logger.error("❌ Error updating idea: %s", response['error'])
            return False
        else:
            self.logger.info("✅ Successfully updated idea: %s", idea_id)
            return True

    async def delete_idea(self, idea_id: str) -> bool:
        """Archive an idea (Notion uses archiving instead of deleting).
        
        Args:
            idea_id: The ID of the idea to archive
            
        Returns:
            Success status
        """
        data = {"archived": True}
        response = await self._make_request(HttpMethod.PATCH, f"pages/{idea_id}", data)
        
        if "error" in response:
            self.logger.error("❌ Error archiving idea: %s", response['error'])
            return False
        else:
            self.logger.info("✅ Successfully archived idea: %s", idea_id)
            return True


async def main():
    """Example usage of the NotionIdeaManager."""
    async with NotionIdeaManager() as manager:
        # Add a new idea
        
        # Get and display all ideas
        all_ideas = await manager.get_all_ideas()
        for idea in all_ideas:
            print(f"💡 {idea['name']} (Status: {idea['status']}, Tags: {', '.join(idea['tags'])})")


if __name__ == "__main__":
    asyncio.run(main())