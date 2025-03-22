import os
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from functools import wraps

# Using standard libraries instead of third-party when possible
import aiohttp
from dotenv import load_dotenv

load_dotenv()

def handle_api_errors(func):
    """Decorator to handle API errors consistently."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except aiohttp.ClientResponseError as e:
            instance = args[0]
            instance.logger.error(f"API request failed: {str(e)}")
            return {"error": f"API request failed: {str(e)}", "status": e.status}
        except aiohttp.ClientError as e:
            instance = args[0]
            instance.logger.error(f"Connection error: {str(e)}")
            return {"error": f"Connection error: {str(e)}"}
        except Exception as e:
            instance = args[0]
            instance.logger.error(f"Unexpected error: {str(e)}")
            return {"error": f"Unexpected error: {str(e)}"}
    return wrapper

class AbstractNotionClient(ABC):
    """Abstract base class for Notion API interactions."""
    
    BASE_URL = "https://api.notion.com/v1"
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("NOTION_SECRET")
        if not self.token:
            raise ValueError("Notion API token is required. Set NOTION_SECRET environment variable or pass token to constructor.")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28"
        }
        
        self.session = None
        self._setup_logger()
    
    def _setup_logger(self):
        """Configure logger for the client."""
        self.logger = logging.getLogger(self.__class__.__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        self.logger.info(f"{self.__class__.__name__} initialized")
    
    async def __aenter__(self):
        """Context manager entry point."""
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit point."""
        if self.session:
            await self.session.close()
    
    @handle_api_errors
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Makes a request to the Notion API.
        
        Args:
            method: HTTP method (get, post, patch, etc.)
            endpoint: API endpoint (without base URL)
            data: Request payload for POST/PATCH requests
            
        Returns:
            API response as dictionary
        """
        if not self.session:
            self.session = aiohttp.ClientSession(headers=self.headers)
            self._managed_session = True
        
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        self.logger.debug(f"Making {method.upper()} request to {url}")
        
        method = method.lower()
        if method == "get":
            async with self.session.get(url) as response:
                response.raise_for_status()
                return await response.json()
        elif method == "post":
            async with self.session.post(url, json=data) as response:
                response.raise_for_status()
                return await response.json()
        elif method == "patch":
            async with self.session.patch(url, json=data) as response:
                response.raise_for_status()
                return await response.json()
        elif method == "delete":
            async with self.session.delete(url) as response:
                response.raise_for_status()
                return await response.json()
        else:
            raise ValueError(f"Unsupported method: {method}")
    
    @abstractmethod
    async def fetch_data(self, *args, **kwargs):
        """Abstract method that subclasses must implement for fetching data."""
        pass
    
    # Example convenience methods
    async def get_page(self, page_id: str) -> Dict[str, Any]:
        """Get a page by ID."""
        return await self._make_request("get", f"pages/{page_id}")
    
    async def update_page(self, page_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Update page properties."""
        return await self._make_request("patch", f"pages/{page_id}", {"properties": properties})
    
    async def query_database(self, database_id: str, filter_params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Query a database with optional filters."""
        return await self._make_request("post", f"databases/{database_id}/query", filter_params or {})

# Example usage
async def main():
    class MyNotionClient(AbstractNotionClient):
        async def fetch_data(self, database_id):
            return await self.query_database(database_id)
    
    async with MyNotionClient() as client:
        # Example: query a database
        results = await client.fetch_data("your-database-id")
        print(results)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())