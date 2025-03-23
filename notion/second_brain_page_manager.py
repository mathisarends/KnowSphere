from typing import List, Dict, Any, Optional, Union
import logging
import asyncio

from notion.core.exceptions.notion_request_error import NotionRequestError
from notion.core.notion_abstract_client import HttpMethod
from notion.core.notion_page_manager import NotionPageManager


class SecondBrainPageManager(NotionPageManager):
    # Database IDs from the schema
    NOTES_DB_ID = "1a6389d5-7bd3-8097-aa38-e93cb052615a"
    PROJECT_DB_ID = "1a6389d5-7bd3-80a3-a60e-cb6bc02f85d6"
    TOPIC_DB_ID = "1a6389d5-7bd3-8034-bc69-fef680261842"
    
    # Property names for relations and fields
    PROJECT_RELATION_NAME = "Projekte"
    TOPIC_RELATION_NAME = "Thema"
    TAGS_PROPERTY_NAME = "Tags"
    SOURCE_PROPERTY_NAME = "Quelle"
    
    # Known status options
    STATUS_OPTIONS = ["Draft", "KI-Draft", "In progress", "To-do", "Done"]
    
    def __init__(self, page_id: str = None, page_name: str = None, token: Optional[str] = None):
        """
        Initialize the SecondBrainManager.
        
        Args:
            page_id: Notion page ID
            page_name: Notion page name (resolved via NotionPages)
            token: Notion API token
        """
        super().__init__(page_id=page_id, page_name=page_name, token=token)
        
        # Cache for relation objects to avoid repeated API calls
        self._project_cache = {}  # name -> id
        self._topic_cache = {}    # name -> id
    
    async def update_page_content(self, new_title: str = None, new_content: str = None, 
                                icon_emoji: str = "🧠", status: str = "KI-Draft") -> str:
        """
        Updates page content including title, content, status and icon.
        
        Args:
            new_title: New title for the page (optional)
            new_content: New content as markdown text (optional)
            icon_emoji: Emoji icon for the page (default: brain emoji)
            status: Status to set (default: KI-Draft)
            
        Returns:
            Status message about the update success
        """
        results = []
        
        # Prepare title and icon update
        update_data = {
            "properties": {},
            "icon": {
                "type": "emoji",
                "emoji": icon_emoji
            }
        }
        
        # Add title if specified
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
        
        # Set status if supplied
        if status:
            if status not in self.STATUS_OPTIONS:
                self.logger.warning("Status '%s' is not in the list of known status options", status)
                
            update_data["properties"]["Status"] = {
                "status": {
                    "name": status
                }
            }
        
        try:
            # Update page (title, icon and status in one request)
            await self._make_request(
                HttpMethod.PATCH,
                f"pages/{self.page_id}",
                update_data
            )
            
            if new_title:
                self.logger.info("Title successfully updated: %s", new_title)
                results.append(f"Title successfully updated: {new_title}")
                # Update attribute if exists
                if hasattr(self, 'title'):
                    self.title = new_title
                    
            self.logger.info("Icon successfully set to %s", icon_emoji)
            results.append(f"Icon successfully set to {icon_emoji}")
            
            self.logger.info("Status successfully set to '%s'", status)
            results.append(f"Status successfully set to '{status}'")
            
            # Update content if specified
            if new_content:
                clear_result = await self.clear_page()
                results.append(clear_result)
                
                append_result = await self.append_content(new_content)
                results.append(append_result)
                
        except NotionRequestError as e:
            error_msg = f"Error updating page: {e.message}"
            self.logger.error(error_msg)
            results.append(error_msg)
        
        return "\n".join(results)

    async def set_status(self, status: str) -> bool:
        """
        Sets the status of a page.
        
        Args:
            status: Status value (e.g., "KI-Draft", "Draft", "In progress")
            
        Returns:
            True on success, False on error
        """
        if status not in self.STATUS_OPTIONS:
            self.logger.warning("Status '%s' is not in the list of known status options", status)
        
        data = {
            "properties": {
                "Status": {
                    "status": {
                        "name": status
                    }
                }
            }
        }
        
        try:
            await self._make_request(
                HttpMethod.PATCH,
                f"pages/{self.page_id}",
                data
            )
            
            self.logger.info("Status successfully set to '%s'", status)
            return True
            
        except NotionRequestError as e:
            self.logger.error("Error setting status: %s", e.message)
            return False

    async def _find_relation_id(self, name: str, database_id: str, cache: Dict[str, str]) -> Optional[str]:
        """
        Helper method to find a relation ID by name.
        
        Args:
            name: Name of the entry to find
            database_id: ID of the database to search
            cache: Cache dictionary for already found IDs
            
        Returns:
            ID of the found entry or None
        """
        # Check if name is already in cache
        if name in cache:
            return cache[name]
        
        # Check if an ID was provided (not a name)
        if name.startswith("1a6389d5-"):
            return name
        
        # Prepare query
        filter_params = {
            "filter": {
                "property": "Name",
                "title": {
                    "equals": name
                }
            },
            "page_size": 1
        }
        
        try:
            # Execute query
            response = await self._make_request(
                HttpMethod.POST,
                f"databases/{database_id}/query",
                filter_params
            )
            
            results = response.get("results", [])
            if not results:
                self.logger.warning("No entry found with name '%s'", name)
                return None
            
            # Extract and cache ID
            relation_id = results[0].get("id")
            if relation_id:
                cache[name] = relation_id
                
            return relation_id
            
        except NotionRequestError as e:
            self.logger.error("Error searching for entry '%s': %s", name, e.message)
            return None

    async def set_projects(self, projects: Union[str, List[str]]) -> bool:
        """
        Sets project relations for a page.
        
        Args:
            projects: Project name/ID or list of project names/IDs
            
        Returns:
            True on success, False on error
        """
        # Convert to list if a single string is provided
        if isinstance(projects, str):
            projects = [projects]
        
        # Find IDs for the project names
        project_ids = []
        for project in projects:
            project_id = await self._find_relation_id(project, self.PROJECT_DB_ID, self._project_cache)
            if project_id:
                project_ids.append(project_id)
            else:
                self.logger.warning("Project '%s' not found and will be skipped", project)
        
        if not project_ids:
            self.logger.warning("No valid projects found")
            return False
        
        # Set relations
        data = {
            "properties": {
                self.PROJECT_RELATION_NAME: {
                    "relation": [{"id": pid} for pid in project_ids]
                }
            }
        }
        
        try:
            await self._make_request(
                HttpMethod.PATCH,
                f"pages/{self.page_id}",
                data
            )
            
            self.logger.info("Projects successfully set: %s", ", ".join(projects))
            return True
            
        except NotionRequestError as e:
            self.logger.error("Error setting projects: %s", e.message)
            return False

    async def set_topics(self, topics: Union[str, List[str]]) -> bool:
        """
        Sets topic relations for a page.
        
        Args:
            topics: Topic name/ID or list of topic names/IDs
            
        Returns:
            True on success, False on error
        """
        # Convert to list if a single string is provided
        if isinstance(topics, str):
            topics = [topics]
        
        # Find IDs for the topic names
        topic_ids = []
        for topic in topics:
            topic_id = await self._find_relation_id(topic, self.TOPIC_DB_ID, self._topic_cache)
            if topic_id:
                topic_ids.append(topic_id)
            else:
                self.logger.warning("Topic '%s' not found and will be skipped", topic)
        
        if not topic_ids:
            self.logger.warning("No valid topics found")
            return False
        
        # Set relations
        data = {
            "properties": {
                self.TOPIC_RELATION_NAME: {
                    "relation": [{"id": tid} for tid in topic_ids]
                }
            }
        }
        
        try:
            await self._make_request(
                HttpMethod.PATCH,
                f"pages/{self.page_id}",
                data
            )
            
            self.logger.info("Topics successfully set: %s", ", ".join(topics))
            return True
            
        except NotionRequestError as e:
            self.logger.error("Error setting topics: %s", e.message)
            return False

    async def set_tags(self, tags: List[str]) -> bool:
        """
        Sets tags for a page.
        
        Args:
            tags: List of tags as strings
            
        Returns:
            True on success, False on error
        """
        data = {
            "properties": {
                self.TAGS_PROPERTY_NAME: {
                    "multi_select": [{"name": tag} for tag in tags]
                }
            }
        }
        
        try:
            await self._make_request(
                HttpMethod.PATCH,
                f"pages/{self.page_id}",
                data
            )
            
            self.logger.info("Tags successfully set: %s", ", ".join(tags))
            return True
            
        except NotionRequestError as e:
            self.logger.error("Error setting tags: %s", e.message)
            return False

    async def set_source(self, source: str) -> bool:
        """
        Sets the source for a page.
        
        Args:
            source: Source text (URL, book name, etc.)
            
        Returns:
            True on success, False on error
        """
        data = {
            "properties": {
                self.SOURCE_PROPERTY_NAME: {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": source
                            }
                        }
                    ]
                }
            }
        }
        
        try:
            await self._make_request(
                HttpMethod.PATCH,
                f"pages/{self.page_id}",
                data
            )
            
            self.logger.info("Source successfully set: %s", source)
            return True
            
        except NotionRequestError as e:
            self.logger.error("Error setting source: %s", e.message)
            return False

    async def get_current_properties(self) -> Dict[str, Any]:
        """
        Retrieves the current properties of the page.
        
        Returns:
            Dictionary with the current properties
        """
        try:
            response = await self._make_request(
                HttpMethod.GET,
                f"pages/{self.page_id}"
            )
            return response.get("properties", {})
            
        except NotionRequestError as e:
            self.logger.error("Error retrieving properties: %s", e.message)
            return {}

    async def get_all_projects(self) -> List[Dict[str, str]]:
        """
        Retrieves all available projects from the projects database.
        
        Returns:
            List of dictionaries with project ID and name
        """
        try:
            # Query the projects database
            response = await self._make_request(
                HttpMethod.POST,
                f"databases/{self.PROJECT_DB_ID}/query",
                {"page_size": 100}  # Adjust page size as needed
            )
            
            projects = []
            for result in response.get("results", []):
                project_id = result.get("id", "")
                project_name = ""
                
                # Extract project name from title property
                if "properties" in result and "Name" in result["properties"]:
                    title_items = result["properties"]["Name"].get("title", [])
                    if title_items:
                        project_name = title_items[0].get("text", {}).get("content", "")
                
                if project_id and project_name:
                    projects.append({"id": project_id, "name": project_name})
                    # Update cache for future use
                    self._project_cache[project_name] = project_id
            
            return projects
            
        except NotionRequestError as e:
            self.logger.error("Error retrieving projects: %s", e.message)
            return []

    async def get_all_topics(self) -> List[Dict[str, str]]:
        """
        Retrieves all available topics from the topics database.
        
        Returns:
            List of dictionaries with topic ID and name
        """
        try:
            # Query the topics database
            response = await self._make_request(
                HttpMethod.POST,
                f"databases/{self.TOPIC_DB_ID}/query",
                {"page_size": 100}  # Adjust page size as needed
            )
            
            topics = []
            for result in response.get("results", []):
                topic_id = result.get("id", "")
                topic_name = ""
                
                # Extract topic name from title property
                if "properties" in result and "Name" in result["properties"]:
                    title_items = result["properties"]["Name"].get("title", [])
                    if title_items:
                        topic_name = title_items[0].get("text", {}).get("content", "")
                
                if topic_id and topic_name:
                    topics.append({"id": topic_id, "name": topic_name})
                    # Update cache for future use
                    self._topic_cache[topic_name] = topic_id
            
            return topics
            
        except NotionRequestError as e:
            self.logger.error("Error retrieving topics: %s", e.message)
            return []
    
    async def get_all_project_names(self) -> List[str]:
        """
        Retrieves all available project names from the projects database.
        
        Returns:
            List of project names
        """
        projects = await self.get_all_projects()
        return [project["name"] for project in projects]

    async def get_all_topic_names(self) -> List[str]:
        """
        Retrieves all available topic names from the topics database.
        
        Returns:
            List of topic names
        """
        topics = await self.get_all_topics()
        return [topic["name"] for topic in topics]
    
    async def get_current_tags(self) -> List[str]:
        """
        Ruft die aktuellen Tags des Eintrags ab.
        
        Returns:
            Liste der Tags als Strings
        """
        properties = await self.get_current_properties()
        
        tags = []
        if "Tags" in properties and "multi_select" in properties["Tags"]:
            for tag in properties["Tags"]["multi_select"]:
                tags.append(tag.get("name", ""))
                
        return tags
    

async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Extract ID from URL: https://www.notion.so/Ultralearning-Strategien-f-r-effektives-Lernen-1bf389d57bd380578ea3c9a5db952a17
    page_id = "1bf389d57bd380578ea3c9a5db952a17"
    
    # Initialize manager with existing page
    entry = SecondBrainPageManager(page_id=page_id)
    print(f"Working with entry: {page_id}")
    
    # Example 1: Get current properties
    current_tags = await entry.get_current_tags()
    print(f"Current tags: {current_tags}")
    
    # Example 2: Change tags (add "Productivity" tag)
    new_tags = current_tags + ["Produktivität"]
    await entry.set_tags(new_tags)
    print(f"Updated tags: {new_tags}")
    
    # Example 3: Set topics for the entry
    await entry.set_topics(["Lernen"])
    print("Topic set to 'Lernen'")
    
    # Example 4: Set project for the entry
    await entry.set_projects(["Thesis"])
    print("Project set to 'Thesis'")
    
    # Example 5: Change source
    await entry.set_source("https://www.scotthyoung.com/blog/ultralearning/")
    print("Source updated")
    
    # topics = await entry.get_all_topic_names()
    # print(topics)
    
    # projects = await entry.get_all_project_names()
    # print(projects)
    
if __name__ == "__main__":
    asyncio.run(main())