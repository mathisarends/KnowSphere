# File: main.py
import asyncio
import logging
import os
from tqdm import tqdm

from notion.second_brain_manager import SecondBrainManager
from agents.graph_processor import DraftLangGraph

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("draft_revision_main")

# Konfiguration
MODEL_NAME = os.environ.get("LLM_MODEL", "gpt-4o-mini")
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "5"))
MAX_DRAFTS = int(os.environ.get("MAX_DRAFTS", "0"))

async def process_all_drafts():
    logger.info("Starte Draft Revision mit LangGraph...")

    sbm = SecondBrainManager()
    await sbm.__aenter__()

    try:
        processor = DraftLangGraph(model_name=MODEL_NAME)
        drafts_generator = sbm.get_draft_entries_generator(batch_size=BATCH_SIZE)

        processed_count = 0
        error_count = 0

        pbar = tqdm(desc="Processing drafts", unit="draft")

        try:
            async for page_manager in drafts_generator:
                result = await processor.process_draft(page_manager)

                processed_count += 1
                pbar.update(1)

                status = result.get("status", "unknown")
                if status == "error" or not result.get("success", False):
                    error_count += 1

                logger.info("[%d] %s - Status: %s", processed_count, page_manager.title, status)

                if MAX_DRAFTS > 0 and processed_count >= MAX_DRAFTS:
                    logger.info("Limit von %d Entwürfen erreicht, beende...", MAX_DRAFTS)
                    break

        except Exception as e:
            logger.error("Fehler während der Verarbeitung: %s", e, exc_info=True)
            raise
        finally:
            pbar.close()

        logger.info("Draft Revision abgeschlossen. Verarbeitet: %d, Fehler: %d", processed_count, error_count)

    except Exception as e:
        logger.error("Fehler im Hauptprozess: %s", e, exc_info=True)
        raise
    finally:
        await sbm.__aexit__(None, None, None)

if __name__ == "__main__":
    asyncio.run(process_all_drafts())
