# File: main.py
import asyncio
import logging
import os
from tqdm import tqdm

from notion.second_brain_manager import SecondBrainManager
from graph_processor import DraftLangGraph

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger("draft_revision_main")

# Konfiguration
MODEL_NAME = os.environ.get("LLM_MODEL", "gpt-4o-mini")
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "5"))
MAX_DRAFTS = int(os.environ.get("MAX_DRAFTS", "0"))

async def process_all_drafts():
    """
    Hauptfunktion zum Verarbeiten aller Entwürfe mit LangGraph.
    """
    logger.info("Starte Draft Revision Process mit LangGraph...")
    
    # SecondBrainManager initialisieren
    sbm = SecondBrainManager()
    await sbm.__aenter__()
    
    try:
        # LangGraph-Prozessor initialisieren
        processor = DraftLangGraph(model_name=MODEL_NAME)
        
        # Generator für Pagination initialisieren
        drafts_generator = sbm.get_draft_entries_generator(batch_size=BATCH_SIZE)
        
        # Statistik
        processed_count = 0
        revised_count = 0
        skipped_count = 0
        error_count = 0
        
        # Progress-Bar
        pbar = tqdm(desc="Processing drafts", unit="draft")
        
        try:
            # Durch alle Drafts iterieren
            async for page_manager in drafts_generator:
                # Entwurf mit LangGraph verarbeiten
                result = await processor.process_draft(page_manager)
                
                processed_count += 1
                pbar.update(1)
                
                # Statistik aktualisieren
                status = result.get("status", "unknown")
                if status == "revised":
                    revised_count += 1
                elif status == "skipped":
                    skipped_count += 1
                else:
                    error_count += 1
                
                # Status loggen
                logger.info(f"[{processed_count}] {page_manager.title} - Status: {status}")
                
                # Begrenzen, falls MAX_DRAFTS gesetzt ist
                if MAX_DRAFTS > 0 and processed_count >= MAX_DRAFTS:
                    logger.info(f"Maximum von {MAX_DRAFTS} Entwürfen erreicht. Beende Verarbeitung.")
                    break
                    
        except Exception as e:
            logger.error(f"Fehler bei der Verarbeitung der Entwürfe: {e}", exc_info=True)
            raise
        finally:
            pbar.close()
        
        # Zusammenfassung ausgeben
        logger.info(f"Draft Revision abgeschlossen.")
        logger.info(f"Insgesamt verarbeitet: {processed_count}")
        logger.info(f"Überarbeitet: {revised_count}")
        logger.info(f"Übersprungen: {skipped_count}")
        logger.info(f"Fehler: {error_count}")
            
    except Exception as e:
        logger.error(f"Fehler bei der Ausführung des Draft Revision Process: {e}", exc_info=True)
        raise
    finally:
        # Ressourcen freigeben
        await sbm.__aexit__(None, None, None)

if __name__ == "__main__":
    asyncio.run(process_all_drafts())