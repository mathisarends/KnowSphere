# Beispiel für die Verwendung des NotionClipboardManager (für Kompatibilität)
from typing import Any, Dict, List, Optional

from notion.core.notion_content_converter import NotionContentConverter
from notion.core.notion_page_writer import NotionPageWriter


class NotionClipboardManager:
    def __init__(self, token: Optional[str] = None):
        self.page_writer = NotionPageWriter(page_name="JARVIS_CLIPBOARD", token=token)
        self.converter = NotionContentConverter()
    
    async def __aenter__(self):
        await self.page_writer.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.page_writer.__aexit__(exc_type, exc_val, exc_tb)
    
    async def append_to_clipboard(self, text: str) -> str:
        return await self.page_writer.append_content(text, add_divider=True)
    
    async def get_clipboard_content(self) -> List[Dict[str, Any]]:
        return await self.page_writer.get_page_content()
    
    async def get_clipboard_text(self) -> str:
        return await self.page_writer.get_page_text()
    
    async def clear_clipboard(self) -> str:
        return await self.page_writer.clear_page()
    
    async def delete_clipboard_block(self, block_id: str) -> bool:
        return await self.page_writer.delete_block(block_id)


async def main():
    """Beispiel für die Verwendung der neuen Klassen."""
    
    # Beispiel 1: Generischer NotionPageWriter
    async with NotionPageWriter(page_name="JARVIS_CLIPBOARD") as page_writer:
        # Inhalt hinzufügen
        await page_writer.append_content("""
# Test Überschrift

Dies ist ein Testabsatz mit **fetten** und *kursiven* Text.

- Listenpunkt 1
- Listenpunkt 2

```python
def hello():
    print("Hallo, Welt!")
```
        """, add_divider=True)
        
        # Seiteninhalt abrufen
        content = await page_writer.get_page_content()
        print(f"{len(content)} Blöcke von der Seite abgerufen")
        
        # Lesbaren Text abrufen
        text = await page_writer.get_page_text()
        print("\nSeiteninhalt:")
        print(text)
        
        # Seite leeren (auskommentiert zur Sicherheit)
        # result = await page_writer.clear_page()
        # print(result)
    
    # Beispiel 2: Kompatibilitätsklasse für bestehenden Code
    async with NotionClipboardManager() as clipboard:
        # Zum Clipboard hinzufügen
        await clipboard.append_to_clipboard("# Kompatibilitätstest\n\nDiese Klasse erhält die alte API.")
        
        # Text abrufen
        text = await clipboard.get_clipboard_text()
        print("\nClipboard-Inhalt (über Kompatibilitätsklasse):")
        print(text)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())