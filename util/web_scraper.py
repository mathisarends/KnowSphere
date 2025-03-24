from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Dict, List, Optional
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('AsyncWebScraper')

class AsyncWebScraper:
    """Class that is used to scrape a website by its url asynchronously"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
    }
        
    @classmethod
    async def create(cls, url):
        """Factory method to create an AsyncWebScraper instance"""
        self = cls()
        self.url = url
        await self._fetch_content()
        return self
    
    async def _fetch_content(self):
        """Fetches the content of the URL using Playwright asynchronously"""
        async with async_playwright() as p:
            # Browser im headless-Modus starten
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                # Setze einen längeren Timeout (60 Sekunden) und verwende domcontentloaded statt networkidle
                logger.info(f"Navigiere zu URL: {self.url}")
                
                # Versuche zuerst mit domcontentloaded, was schneller ist
                try:
                    await page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
                    logger.info("Seite wurde mit 'domcontentloaded' geladen")
                except PlaywrightTimeoutError:
                    logger.warning("Timeout bei 'domcontentloaded', versuche es ohne wait_until")
                    # Zweiter Versuch ohne wait_until
                    await page.goto(self.url, timeout=60000)
                    logger.info("Seite wurde ohne 'wait_until' geladen")
                
                # Warte noch kurz, damit JavaScript geladen werden kann
                await asyncio.sleep(2)
                
                # Extrahiere den gesamten Seiteninhalt
                page_source = await page.content()
                logger.info(f"Seiten-Content erfolgreich abgerufen (Länge: {len(page_source)})")
                
            except Exception as e:
                logger.error(f"Fehler beim Laden der Seite: {str(e)}")
                # Setze einen leeren HTML-String im Fehlerfall
                page_source = "<html><body><p>Error loading page</p></body></html>"
            finally:
                await browser.close()
        
        # Verarbeite den Seiteninhalt mit BeautifulSoup
        soup = BeautifulSoup(page_source, 'html.parser')
        self.title = soup.title.string if soup.title else "No title found"
        logger.info(f"Seitentitel: {self.title}")
        
        # Speichere das Soup-Objekt für weitere Verarbeitung
        self.soup = soup
        
        # Extrahiere den Text der Seite
        for irrelevant in soup.body(["script", "style", "img", "input"]):
            irrelevant.decompose()
        self.text = soup.body.get_text(separator="\n", strip=True)
    
    def get_transcript(self) -> Optional[str]:
        """
        Extrahiert das Transkript von einer Snipd-Seite
        
        Returns:
            String mit dem Transkript oder None, wenn keines gefunden wurde
        """
        # Suche nach dem Transkript-Element mit der Klasse "transcript-text"
        transcript_div = self.soup.find('div', class_='transcript-text')
        
        if transcript_div:
            logger.info("Transkript mit Klasse 'transcript-text' gefunden")
            return transcript_div.get_text(separator="\n", strip=True)
        
        # Versuche alternative Selektoren
        logger.info("Suche nach alternativen Transkript-Elementen...")
        
        # 1. Suche nach einem Element, dessen Klassenname "transcript" enthält
        transcript_elements = self.soup.find_all(lambda tag: tag.name == 'div' and 
                                               tag.get('class') and 
                                               any('transcript' in c.lower() for c in tag.get('class')))
        
        if transcript_elements:
            logger.info(f"Alternatives Transkript gefunden mit Klasse: {transcript_elements[0].get('class')}")
            return transcript_elements[0].get_text(separator="\n", strip=True)
        
        # 2. Versuche es mit einem breiteren Ansatz - suche nach <p> Tags in bestimmten Abschnitten
        transcript_section = self.soup.find('section', class_='transcript') or self.soup.find('div', id='transcript')
        if transcript_section:
            paragraphs = transcript_section.find_all('p')
            if paragraphs:
                logger.info(f"Transkript aus Paragraphen extrahiert ({len(paragraphs)} Absätze)")
                return "\n".join(p.get_text() for p in paragraphs)
        
        # Debugging: Zeige alle großen Textblöcke
        logger.info("Kein Transkript mit den Standardselektoren gefunden. Suche nach großen Textblöcken...")
        
        # Finde alle div-Elemente mit viel Text
        possible_transcript_divs = []
        for div in self.soup.find_all('div'):
            text = div.get_text(strip=True)
            if len(text) > 500:  # Mindestens 500 Zeichen, um ein Transkript zu sein
                possible_transcript_divs.append((div, len(text)))
        
        # Sortiere nach Textlänge
        possible_transcript_divs.sort(key=lambda x: x[1], reverse=True)
        
        # Wenn es mindestens ein großes Textelement gibt, nimm das größte
        if possible_transcript_divs:
            logger.info(f"Mögliches Transkript gefunden (größtes Textelement: {possible_transcript_divs[0][1]} Zeichen)")
            return possible_transcript_divs[0][0].get_text(separator="\n", strip=True)
        
        logger.warning("Kein Transkript gefunden")
        return None


async def scrape_snipd_url(url: str) -> Optional[str]:
    """
    Hilfsfunktion zum Scrapen eines einzelnen Snipd-Links
    
    Args:
        url: Die Snipd-URL
        
    Returns:
        Das extrahierte Transkript oder None
    """
    try:
        scraper = await AsyncWebScraper.create(url)
        return scraper.get_transcript()
    except Exception as e:
        logger.error(f"Fehler beim Scrapen von {url}: {str(e)}")
        return None


# Beispielverwendung
if __name__ == "__main__":
    async def main():
        # Beispiel mit direkter URL
        test_url = "https://share.snipd.com/snip/4b28fb29-2310-46a7-881e-b59d27a3b415"
        
        # Einzelne URL testen
        logger.info(f"Teste URL: {test_url}")
        transcript = await scrape_snipd_url(test_url)
        
        if transcript:
            logger.info(f"Transkript gefunden ({len(transcript)} Zeichen)")
            logger.info(f"Erste 200 Zeichen: {transcript[:200]}...")
        else:
            logger.warning("Kein Transkript gefunden")
    
    asyncio.run(main())