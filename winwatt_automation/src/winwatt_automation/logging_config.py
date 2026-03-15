from loguru import logger


def configure_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level=level)
