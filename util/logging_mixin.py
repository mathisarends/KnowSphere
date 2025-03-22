import logging

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
setup_logging()

class LoggingMixin:
    @property
    def logger(self):
        if not hasattr(self, '_logger'):
            # Klassenname als Logger-Name verwenden
            self._logger = logging.getLogger(self.__class__.__name__)
        return self._logger