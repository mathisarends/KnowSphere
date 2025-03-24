from typing import Dict, List, Optional, Tuple
from notion.core.notion_page_manager import NotionPageManager


class SnipdPageManager(NotionPageManager):
    
    def __init__(self, page_id: str = None, page_name: str = None, token: Optional[str] = None):
        super().__init__(page_id=page_id, page_name=page_name, token=token)
        
    async def get_snipd_links(self) -> List[Dict[str, str]]:
        """
        Extract all Snipd links from the page content.
        
        Returns:
            List of dictionaries with timestamp, link, and duration information
            [
                {
                    "timestamp": "13:08",
                    "link": "https://share.snipd.com/snip/4b28fb29-2310-46a7-881e-b59d27a3b415",
                    "duration": "1min"
                },
                ...
            ]
        """
        page_content = await self.get_page_content()
        snips = []
        
        for block in page_content:
            # Check if it's a heading_3 block (where snips are stored)
            if block.get("type") == "heading_3":
                heading_data = block.get("heading_3", {})
                rich_text = heading_data.get("rich_text", [])
                
                if rich_text:
                    timestamp, link, duration = self._parse_snipd_heading(rich_text)
                    
                    if timestamp and link:
                        snips.append({
                            "timestamp": timestamp,
                            "link": link,
                            "duration": duration,
                            "block_id": block.get("id")
                        })
        
        return snips
    
    def _parse_snipd_heading(self, rich_text) -> Tuple[str, str, str]:
        """
        Parse the rich_text array from a heading to extract timestamp, link, and duration.
        
        Args:
            rich_text: The rich_text array from a heading_3 block
            
        Returns:
            Tuple of (timestamp, link, duration)
        """
        timestamp = ""
        link = ""
        duration = ""
        
        # First segment typically contains timestamp and link
        if rich_text and len(rich_text) > 0:
            first_segment = rich_text[0]
            if first_segment.get("type") == "text":
                # Extract timestamp from text content (usually in format [XX:XX])
                text_content = first_segment.get("text", {}).get("content", "")
                if text_content.startswith("[") and "]" in text_content:
                    timestamp = text_content.strip("[]")
                
                # Extract link if present
                link_data = first_segment.get("text", {}).get("link", {})
                if link_data:
                    link = link_data.get("url", "")
        
        # Second segment typically contains duration (e.g., "1min Snip")
        if len(rich_text) > 1:
            second_segment = rich_text[1]
            if second_segment.get("type") == "text":
                duration_text = second_segment.get("text", {}).get("content", "").strip()
                if "min" in duration_text:
                    # Extract just the duration part (e.g., "1min" from "1min Snip")
                    duration = duration_text.split()[0]
                    
        return timestamp, link, duration