from abc import ABC, abstractmethod
from typing import Optional, Dict, Tuple
import asyncio

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from util.logging_mixin import LoggingMixin

class PageLoader(LoggingMixin):
    """
    Verantwortlich für das Laden und Parsen von Webseiten.
    Diese Klasse ist unabhängig von Extraktionsstrategien und kann wiederverwendet werden.
    """
    
    @classmethod
    async def load_page(cls, url: str, timeout: int = 30000) -> Tuple[str, BeautifulSoup, str, str]:
        """
        Lädt eine Webseite und gibt den HTML-Inhalt, das BeautifulSoup-Objekt,
        den Titel und den extrahierten Text zurück.
        """
        instance = cls()
        page_source = "<html><body><p>Error loading page</p></body></html>"
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                instance.logger.info("Navigating to URL: %s", url)
                
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                    instance.logger.info("Page loaded with 'domcontentloaded'")
                except PlaywrightTimeoutError:
                    instance.logger.warning("Timeout with 'domcontentloaded', trying without wait_until")
                    await page.goto(url, timeout=timeout*2)
                    instance.logger.info("Page loaded without 'wait_until'")
                
                await asyncio.sleep(2)
                page_source = await page.content()
                instance.logger.info("Page content successfully retrieved (Length: %d)", len(page_source))
                
            except Exception as e:
                instance.logger.error("Error loading page: %s", str(e))
            finally:
                await browser.close()
        
        # HTML mit BeautifulSoup parsen
        soup = BeautifulSoup(page_source, 'html.parser')
        
        # Titel extrahieren
        title = soup.title.string if soup.title else "No title found"
        instance.logger.info("Page title: %s", title)
        
        # Text extrahieren
        text_soup = BeautifulSoup(page_source, 'html.parser')
        for irrelevant in text_soup.find_all(["script", "style", "img", "input"]):
            irrelevant.decompose()
        text = text_soup.get_text(separator="\n", strip=True)
        
        return page_source, soup, title, text

class ScrapingStrategy(ABC, LoggingMixin):
    """Abstrakte Basisklasse für Scraping-Strategien"""
    
    @abstractmethod
    async def extract(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extrahiert Daten aus dem BeautifulSoup-Objekt"""
        pass


class SnipdTranscriptScrapingStrategy(ScrapingStrategy):
    """Strategie zum Extrahieren von Transkripten"""
    
    async def extract(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extrahiert Transkript-Text aus verschiedenen möglichen Strukturen"""
        transcript_div = soup.find('div', class_='transcript-text')
        
        if transcript_div:
            self.logger.info("Transcript found with class 'transcript-text'")
            return {
                "transcript": transcript_div.get_text(separator="\n", strip=True),
                "source": "transcript-text-class"
            }
        
        self.logger.info("Searching for alternative transcript elements...")
        
        transcript_elements = soup.find_all(
            lambda tag: tag.name == 'div' and 
            tag.get('class') and 
            any('transcript' in c.lower() for c in tag.get('class'))
        )
        
        if transcript_elements:
            self.logger.info("Alternative transcript found with class: %s", transcript_elements[0].get('class'))
            return {
                "transcript": transcript_elements[0].get_text(separator="\n", strip=True),
                "source": "class-containing-transcript"
            }
        
        transcript_section = soup.find('section', class_='transcript') or soup.find('div', id='transcript')
        if transcript_section:
            paragraphs = transcript_section.find_all('p')
            if paragraphs:
                self.logger.info("Transcript extracted from paragraphs (%d paragraphs)", len(paragraphs))
                return {
                    "transcript": "\n".join(p.get_text() for p in paragraphs),
                    "source": "transcript-section-paragraphs"
                }
        
        self.logger.info("No transcript found with standard selectors. Searching for large text blocks...")
        
        possible_transcript_divs = []
        for div in soup.find_all('div'):
            text = div.get_text(strip=True)
            if len(text) > 500:
                possible_transcript_divs.append((div, len(text)))
        
        if not possible_transcript_divs:
            self.logger.warning("No transcript found")
            return None
            
        possible_transcript_divs.sort(key=lambda x: x[1], reverse=True)
        self.logger.info("Possible transcript found (largest text element: %d characters)", 
                   possible_transcript_divs[0][1])
        return {
            "transcript": possible_transcript_divs[0][0].get_text(separator="\n", strip=True),
            "source": "largest-text-block"
        }


class AsyncWebScraper(LoggingMixin):
    """
    Universeller Web-Scraper, der verschiedene Extraktionsstrategien unterstützt.
    Kann sowohl mit URLs als auch direkt mit HTML-Inhalten arbeiten.
    """
    
    def __init__(self):
        super().__init__()
        self.url = None
        self.html = None
        self.soup = None
        self.title = None
        self.text = None
        self.strategy = None
        
    def set_strategy(self, strategy: ScrapingStrategy):
        """Setzt die zu verwendende Strategie"""
        self.strategy = strategy
        return self
        
    @classmethod
    async def from_url(cls, url: str, timeout: int = 30000):
        """
        Factory-Methode zum Erstellen einer AsyncWebScraper-Instanz von einer URL
        
        Args:
            url: Die zu ladende URL
            timeout: Timeout für das Laden der Seite in Millisekunden
        """
        scraper = cls()
        scraper.url = url
        
        scraper.html, scraper.soup, scraper.title, scraper.text = await PageLoader.load_page(url, timeout)
        
        return scraper
    
    async def extract(self, default_strategy_class=SnipdTranscriptScrapingStrategy) -> Optional[str]:
        """
        Extrahiert den Haupttextinhalt mit der aktuellen oder einer Standard-Strategie.
        """
        if not self.soup:
            self.logger.error("No content available.")
            return None

        if not self.strategy:
            self.strategy = default_strategy_class()

        result = await self.strategy.extract(self.soup)
        if not result:
            return None

        content_keys = ["transcript", "content", "text", "main_content", "body"]

        for key in content_keys:
            if key in result:
                return result[key]

        first_value = next(iter(result.values()), None)
        if isinstance(first_value, str):
            return first_value

        self.logger.warning("Could not find a string content in the result")
        return None


async def demo():
    scraper = await AsyncWebScraper.from_url("https://share.snipd.com/snip/4b4c2932-43e5-422c-b78f-6399030a67ad")
    content = await scraper.extract()
    print(content)
    
if __name__ == "__main__":
    asyncio.run(demo())