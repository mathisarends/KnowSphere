
from typing import List

from notion.core.notion_config import NOTION_PAGES, NOTION_DATABASES, PROJECT_PAGES

class NotionPages:
    @staticmethod
    def get_page_id(name: str) -> str:
        return NOTION_PAGES.get(name.upper(), "UNKNOWN_PAGE")

    @staticmethod
    def get_database_id(name: str) -> str:
        return NOTION_DATABASES.get(name.upper(), "UNKNOWN_DATABASE")
    
    @staticmethod
    def get_project_name_by_id(page_id: str) -> str:
        for name, id in PROJECT_PAGES.items():
            if id == page_id:
                return name
        return "UNKNOWN_PROJECT"

    @staticmethod
    def list_all_project_pages() -> List[str]:
        return list(PROJECT_PAGES.values())