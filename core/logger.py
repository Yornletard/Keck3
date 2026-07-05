import logging
import logging.handlers
from config import LOG_LEVEL, LOG_FORMAT, LOG_FILE, LOGS_DIR

def setup_logger(name: str) -> logging.Logger:
    """Configure et retourne un logger."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, LOG_LEVEL))

    if not logger.handlers:
        # Handler fichier
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE,
            maxBytes=10485760,
            backupCount=5
        )
        file_handler.setLevel(getattr(logging, LOG_LEVEL))
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(file_handler)

        # Handler console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, LOG_LEVEL))
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        logger.addHandler(console_handler)

    return logger

logger = setup_logger('Keck3')
