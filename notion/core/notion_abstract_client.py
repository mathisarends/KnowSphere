import os
import enum
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Union

import aiohttp
from dotenv import load_dotenv

from util.logging_mixin import LoggingMixin

load_dotenv()

class HttpMethod(enum.Enum):
    """HTTP methods enum for API requests."""
    GET = "get"
    POST = "post"
    PATCH = "patch"
    DELETE = "delete"


class AbstractNotionClient(ABC, LoggingMixin):
    """Abstract base class for Notion API interactions."""
    
    BASE_URL = "https://api.notion.com/v1"
    NOTION_VERSION = "2022-06-28"
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("NOTION_SECRET", "")
        if not self.token:
            raise ValueError("Notion API token is required. Set NOTION_SECRET environment variable or pass token to constructor.")
        
        # Set up headers for all requests
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": self.NOTION_VERSION
        }
        
        # Session will be initialized when needed
        self.session = None
    
    async def __aenter__(self):
        """Context manager entry point."""
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point."""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def _make_request(self, method: Union[HttpMethod, str], endpoint: str, data: Optional[Dict[str, Any]] = None):
        if not self.session:
            self.session = aiohttp.ClientSession(headers=self.headers)
        
        # Build the URL and normalize the method
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        if isinstance(method, HttpMethod):
            method_str = method.value
        else:
            method_str = str(method).lower()
        
        self.logger.debug("Making %s request to %s", method_str.upper(), url)
        
        # Make the request with appropriate error handling
        try:
            if method_str == HttpMethod.GET.value:
                async with self.session.get(url) as response:
                    response.raise_for_status()
                    return await response.json()
                    
            elif method_str == HttpMethod.POST.value:
                async with self.session.post(url, json=data) as response:
                    response.raise_for_status()
                    return await response.json()
                    
            elif method_str == HttpMethod.PATCH.value:
                async with self.session.patch(url, json=data) as response:
                    response.raise_for_status()
                    return await response.json()
                    
            elif method_str == HttpMethod.DELETE.value:
                async with self.session.delete(url) as response:
                    response.raise_for_status()
                    return await response.json()
                    
            else:
                raise ValueError(f"Unsupported method: {method_str}")
                
        except aiohttp.ClientResponseError as e:
            self.logger.error("API request failed: %s", str(e))
            return {"error": f"API request failed: {str(e)}", "status": e.status}
            
        except aiohttp.ClientError as e:
            self.logger.error("Connection error: %s", str(e))
            return {"error": f"Connection error: {str(e)}"}
            
        except Exception as e:
            self.logger.error("Unexpected error: %s", str(e))
            return {"error": f"Unexpected error: {str(e)}"}
    
    @abstractmethod
    async def fetch_data(self, *args, **kwargs):
        """Abstract method that subclasses must implement for fetching data."""
        pass
    
    async def get_page(self, page_id: str):
        """Get a page by ID."""
        return await self._make_request(HttpMethod.GET, f"pages/{page_id}")
    
    async def update_page(self, page_id: str, properties: Dict[str, Any]):
        """Update page properties."""
        return await self._make_request(HttpMethod.PATCH, f"pages/{page_id}", {"properties": properties})
    
    async def query_database(self, database_id: str, filter_params=None, sorts=None, start_cursor=None, page_size=None):
        """Query a database with optional filters."""
        data = {}
        if filter_params:
            data["filter"] = filter_params
        if sorts:
            data["sorts"] = sorts
        if start_cursor:
            data["start_cursor"] = start_cursor
        if page_size:
            data["page_size"] = page_size
            
        return await self._make_request(HttpMethod.POST, f"databases/{database_id}/query", data)
