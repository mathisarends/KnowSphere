import asyncio
from typing import Optional, Callable

from notion.core.notion_pages import NotionPages
from notion.todo.models import Todo, TodoPriority
from notion.todo.notion_todo_repository import NotionTodoRepository
from notion.todo.models import TodoStatus
from util.logging_mixin import LoggingMixin

class TodoService(LoggingMixin):
    """Business logic for Todo operations"""
    
    def __init__(self, repository: NotionTodoRepository, logger: Optional[Callable] = None):
        self.repository = repository
        self.logger = logger or print
    
    async def add_todo(self, title: str, priority: str = TodoPriority.MEDIUM.value, 
                       project_name: Optional[str] = None) -> str:
        try:
            project_ids = []
            if project_name:
                project_id = NotionPages.get_page_id(project_name)
                if project_id != "UNKNOWN_PROJECT":
                    project_ids = [project_id]
            
            todo = Todo(
                id="",
                title=title,
                priority=priority,
                status=TodoStatus.NOT_STARTED.value,
                done=False,
                project_ids=project_ids,
                project_names=[project_name] if project_name and project_id != "UNKNOWN_PROJECT" else []
            )
            
            # Create in Notion
            result = await self.repository.create_todo(todo)
            
            if not result:
                log_message = f"❌ Error adding TODO: {title}"
                self.logger.error(log_message)
                return log_message
                
            log_message = f"✅ TODO added: {title}"
            self.logger.error(log_message)
            return f"✅ TODO '{title}' added successfully."
            
        except Exception as e:
            log_message = f"❌ API call failed: {str(e)}"
            self.logger.error(log_message)
            return log_message
            
            
    async def _delete_completed_todos(self) -> None:
        try:
            results = await self.repository.fetch_all_todos()
            
            completed_todo_ids = [
                item.get("id") for item in results
                if item.get("properties", {}).get("Fertig", {}).get("checkbox", False)
            ]
            
            if not completed_todo_ids:
                return
                
            delete_tasks = [self.repository.delete_todo(todo_id) for todo_id in completed_todo_ids]
            results = await asyncio.gather(*delete_tasks, return_exceptions=True)
            
            deleted_count = sum(1 for result in results if result is True)
            
            if deleted_count > 0:
                self.logger.error(f"✅ {deleted_count} abgeschlossene TODOs gelöscht")
                
        except Exception as e:
            self.logger.error(f"❌ Fehler beim Aufräumen der TODOs: {str(e)}")
    