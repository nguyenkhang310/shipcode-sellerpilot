import logging


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    # Avoid logging request URLs or future model payloads through HTTPX.
    logging.getLogger("httpx").setLevel(logging.WARNING)
