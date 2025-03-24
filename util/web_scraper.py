from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from typing import Optional
import asyncio
from util.logging_mixin import LoggingMixin

class AsyncWebScraper(LoggingMixin):
    """Asynchronously scrapes websites by URL"""
        
    @classmethod
    async def create(cls, url):
        """Factory method to create an AsyncWebScraper instance"""
        self = cls()
        self.url = url
        await self._fetch_content()
        return self
    
    async def _fetch_content(self):
        """Fetches the content of the URL using Playwright"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            page_source = "<html><body><p>Error loading page</p></body></html>"

            try:
                self.logger.info("Navigating to URL: %s", self.url)
                
                try:
                    await page.goto(self.url, wait_until="domcontentloaded", timeout=30000)
                    self.logger.info("Page loaded with 'domcontentloaded'")
                except PlaywrightTimeoutError:
                    self.logger.warning("Timeout with 'domcontentloaded', trying without wait_until")
                    await page.goto(self.url, timeout=60000)
                    self.logger.info("Page loaded without 'wait_until'")
                
                await asyncio.sleep(2)
                page_source = await page.content()
                self.logger.info("Page content successfully retrieved (Length: %d)", len(page_source))
                
            except Exception as e:
                self.logger.error("Error loading page: %s", str(e))
            finally:
                await browser.close()
        
        soup = BeautifulSoup(page_source, 'html.parser')
        self.title = soup.title.string if soup.title else "No title found"
        self.logger.info("Page title: %s", self.title)
        
        self.soup = soup
        
        for irrelevant in soup.body(["script", "style", "img", "input"]):
            irrelevant.decompose()
        self.text = soup.body.get_text(separator="\n", strip=True)
    
    def get_transcript(self) -> Optional[str]:
        """
        Extracts transcript from a Snipd page
        
        Returns:
            String with transcript or None if not found
        """
        transcript_div = self.soup.find('div', class_='transcript-text')
        
        if transcript_div:
            self.logger.info("Transcript found with class 'transcript-text'")
            return transcript_div.get_text(separator="\n", strip=True)
        
        self.logger.info("Searching for alternative transcript elements...")
        
        transcript_elements = self.soup.find_all(
            lambda tag: tag.name == 'div' and 
            tag.get('class') and 
            any('transcript' in c.lower() for c in tag.get('class'))
        )
        
        if transcript_elements:
            self.logger.info("Alternative transcript found with class: %s", transcript_elements[0].get('class'))
            return transcript_elements[0].get_text(separator="\n", strip=True)
        
        transcript_section = self.soup.find('section', class_='transcript') or self.soup.find('div', id='transcript')
        if transcript_section:
            paragraphs = transcript_section.find_all('p')
            if paragraphs:
                self.logger.info("Transcript extracted from paragraphs (%d paragraphs)", len(paragraphs))
                return "\n".join(p.get_text() for p in paragraphs)
        
        self.logger.info("No transcript found with standard selectors. Searching for large text blocks...")
        
        possible_transcript_divs = []
        for div in self.soup.find_all('div'):
            text = div.get_text(strip=True)
            if len(text) > 500:
                possible_transcript_divs.append((div, len(text)))
        
        if not possible_transcript_divs:
            self.logger.warning("No transcript found")
            return None
            
        possible_transcript_divs.sort(key=lambda x: x[1], reverse=True)
        self.logger.info("Possible transcript found (largest text element: %d characters)", 
                   possible_transcript_divs[0][1])
        return possible_transcript_divs[0][0].get_text(separator="\n", strip=True)