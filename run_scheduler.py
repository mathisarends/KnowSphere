# scheduler_manager.py
import asyncio
import logging
from task_scheduler import TaskScheduler
from main import process_all_drafts

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("scheduler_manager")

def run_draft_process():
    logger.info("Starte geplante Draft-Revision...")
    asyncio.run(process_all_drafts())
    logger.info("Geplante Draft-Revision abgeschlossen")

if __name__ == "__main__":
    scheduler = TaskScheduler()
    
    task_name = scheduler.add_midnight_task(run_draft_process, "DraftRevisionTask")
    logger.info("Task '%s' zur Ausführung um Mitternacht geplant", task_name)
    
    try:
        scheduler.start()
        logger.info("Scheduler gestartet und läuft im Hintergrund")
        
        while True:
            import time
            time.sleep(21600)
            
    except KeyboardInterrupt:
        logger.info("Scheduler wird beendet...")
        scheduler.stop()