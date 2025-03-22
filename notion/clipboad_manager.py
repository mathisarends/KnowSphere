from typing import List, Dict, Any, Optional

from notion.core.markdown_parser import NotionMarkdownParser
from notion.core.notion_abstract_client import AbstractNotionClient, HttpMethod
from notion.core.notion_pages import NotionPages

class NotionClipboardManager(AbstractNotionClient):
    """Manager for handling a Notion clipboard page."""
    
    def __init__(self, token: Optional[str] = None):
        super().__init__(token=token)
        self.clipboard_page_id = NotionPages.get_page_id("JARVIS_CLIPBOARD")
    
    async def fetch_data(self, *args, **kwargs) -> Any:
        """Implementation of the abstract method required by AbstractNotionClient."""
        return await self.get_clipboard_content()
    
    async def append_to_clipboard(self, text: str) -> str:
        """Appends formatted text to the clipboard page with a divider.
        
        Args:
            text: Markdown text to append to the clipboard
            
        Returns:
            Success or error message
        """
        divider_block = {
            "type": "divider",
            "divider": {}
        }
        
        content_blocks = NotionMarkdownParser.parse_markdown(text)
        
        data = {
            "children": [divider_block] + content_blocks
        }
        
        response = await self._make_request(
            HttpMethod.PATCH, 
            f"blocks/{self.clipboard_page_id}/children", 
            data
        )
        
        if "error" in response:
            self.logger.error("Error adding text: %s", response.get('error'))
            return f"Error adding text: {response.get('error')}"
        else:
            self.logger.info("Text successfully added to clipboard page.")
            return "Text successfully added to clipboard page."
    
    async def get_clipboard_content(self) -> List[Dict[str, Any]]:
        """Retrieves all content from the clipboard page.
        
        Returns:
            List of block objects or empty list on error
        """
        response = await self._make_request(
            HttpMethod.GET, 
            f"blocks/{self.clipboard_page_id}/children"
        )
        
        if "error" in response:
            self.logger.error("Error retrieving clipboard content: %s", response.get('error'))
            return []
        
        return response.get("results", [])
    
    async def get_clipboard_text(self) -> str:
        """Retrieves clipboard content and converts it to readable text.
        
        Returns:
            Text representation of clipboard content or error message
        """
        blocks = await self.get_clipboard_content()
        
        if not blocks:
            return "No content found or error retrieving content."
        
        text_parts = []
        
        for block in blocks:
            block_type = block.get("type", "")
            
            if block_type == "paragraph":
                paragraph_text = self._extract_text_from_rich_text(
                    block.get("paragraph", {}).get("rich_text", [])
                )
                if paragraph_text:
                    text_parts.append(paragraph_text)
            
            elif block_type == "heading_1":
                heading_text = self._extract_text_from_rich_text(
                    block.get("heading_1", {}).get("rich_text", [])
                )
                if heading_text:
                    text_parts.append(f"# {heading_text}")
            
            elif block_type == "heading_2":
                heading_text = self._extract_text_from_rich_text(
                    block.get("heading_2", {}).get("rich_text", [])
                )
                if heading_text:
                    text_parts.append(f"## {heading_text}")
            
            elif block_type == "heading_3":
                heading_text = self._extract_text_from_rich_text(
                    block.get("heading_3", {}).get("rich_text", [])
                )
                if heading_text:
                    text_parts.append(f"### {heading_text}")
            
            elif block_type == "bulleted_list_item":
                item_text = self._extract_text_from_rich_text(
                    block.get("bulleted_list_item", {}).get("rich_text", [])
                )
                if item_text:
                    text_parts.append(f"• {item_text}")
            
            elif block_type == "numbered_list_item":
                item_text = self._extract_text_from_rich_text(
                    block.get("numbered_list_item", {}).get("rich_text", [])
                )
                if item_text:
                    # We don't know the actual number here, so we use bullet points
                    text_parts.append(f"1. {item_text}")
            
            elif block_type == "divider":
                text_parts.append("---")
            
            elif block_type == "code":
                code_text = self._extract_text_from_rich_text(
                    block.get("code", {}).get("rich_text", [])
                )
                language = block.get("code", {}).get("language", "")
                if code_text:
                    text_parts.append(f"```{language}\n{code_text}\n```")
            
            # Add more block types as needed
        
        return "\n\n".join(text_parts)
    
    def _extract_text_from_rich_text(self, rich_text: List[Dict[str, Any]]) -> str:
        """Extract plain text from Notion's rich_text format.
        
        Args:
            rich_text: List of rich text objects from Notion API
            
        Returns:
            Plain text representation
        """
        return "".join([text.get("plain_text", "") for text in rich_text])
    
    async def clear_clipboard(self) -> str:
        """Clears all content from the clipboard page.
        
        Returns:
            Success or error message
        """
        # First, get all blocks on the page
        blocks = await self.get_clipboard_content()
        
        if not blocks:
            return "No content to clear or error retrieving content."
        
        # Delete each block one by one
        deleted_count = 0
        for block in blocks:
            block_id = block.get("id")
            if not block_id:
                continue
                
            response = await self._make_request(
                HttpMethod.DELETE,
                f"blocks/{block_id}"
            )
            
            if "error" not in response:
                deleted_count += 1
        
        if deleted_count == len(blocks):
            self.logger.info("Successfully cleared all %d blocks from clipboard.", deleted_count)
            return f"Successfully cleared all {deleted_count} blocks from clipboard."
        else:
            self.logger.warning("Partially cleared clipboard. Deleted %d of %d blocks.", deleted_count, len(blocks))
            return f"Partially cleared clipboard. Deleted {deleted_count} of {len(blocks)} blocks."
    
    async def delete_clipboard_block(self, block_id: str) -> bool:
        """Deletes a specific block from the clipboard.
        
        Args:
            block_id: ID of the block to delete
            
        Returns:
            True if deletion was successful, False otherwise
        """
        response = await self._make_request(
            HttpMethod.DELETE,
            f"blocks/{block_id}"
        )
        
        if "error" in response:
            self.logger.error("Error deleting block %s: %s", block_id, response.get('error'))
            return False
        else:
            self.logger.info("Successfully deleted block %s.", block_id)
            return True


async def main():
    """Example usage of the NotionClipboardManager."""
    
    async with NotionClipboardManager() as manager:
        # Append to clipboard
        await manager.append_to_clipboard("""
# Test Heading

This is a test paragraph with some **bold** and *italic* text.

- List item 1
- List item 2

```python
def hello():
    print("Hello, world!")
```

Immer mehr tests
        """)
        
        # Get clipboard content
        content = await manager.get_clipboard_content()
        print(f"Retrieved {len(content)} blocks from clipboard")
        
        # Get readable text
        text = await manager.get_clipboard_text()
        print("\nClipboard Content:")
        print(text)
        
        # Clear clipboard (uncomment to use)
        # result = await manager.clear_clipboard()
        # print(result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())