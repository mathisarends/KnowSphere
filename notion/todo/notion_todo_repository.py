from typing import Any, Dict, List, Optional

from notion.core.notion_abstract_client import AbstractNotionClient, HttpMethod
from notion.todo.models import Todo


class NotionTodoRepository(AbstractNotionClient):
    def __init__(self, database_id: str, token: Optional[str] = None):
        # Call the parent class constructor
        super().__init__(token=token)
        self.database_id = database_id
    
    async def fetch_all_todos(self) -> List[Dict[str, Any]]:
        response = await self._make_request(HttpMethod.POST, f"databases/{self.database_id}/query")
        
        if "error" in response:
            self.logger.error("Error fetching todos: %s", response['error'])
            return []
            
        return response.get("results", [])
    
    async def create_todo(self, todo: Todo) -> Dict[str, Any]:
        """Create a new todo in Notion"""
        data = {
            "parent": {"database_id": self.database_id},
            "properties": {
                "Titel": {"title": [{"text": {"content": todo.title}}]},
                "Priorität": {"select": {"name": todo.priority}},
                "Status": {"status": {"name": todo.status}},
                "Fertig": {"checkbox": todo.done}
            }
        }
        
        if todo.project_ids:
            data["properties"]["Projekt"] = {
                "relation": [{"id": project_id} for project_id in todo.project_ids]
            }
            
        response = await self._make_request(HttpMethod.POST, "pages", data)
        return response.json() if response.status_code == 200 else None
    
    async def delete_todo(self, todo_id: str) -> bool:
        """Delete a todo by ID"""
        response = await self._make_request(HttpMethod.DELETE, f"pages/{todo_id}")
        return response.status_code == 200
    
async def main():
    """Main function to test the NotionTodoRepository"""
    async with NotionTodoRepository("1a7389d5-7bd3-807a-8451-e66ed94f8cd0") as repository:
        todos = await repository.fetch_all_todos()
        print(todos)
    
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())