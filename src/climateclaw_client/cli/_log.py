"""Log level handling for the shell."""

import logging

from rich.logging import RichHandler

TRACE = 5
logging.addLevelName(TRACE, "TRACE")

LEVELS = (logging.INFO, logging.DEBUG, TRACE)

logger = logging.getLogger("climateclaw_client")


def resolve_level(
    log: str | None = None,
    verbose: int = 0,
    debug: bool = False,
    trace: bool = False,
) -> int:
    """Get the log level, ``--trace`` > ``--debug`` > ``--log`` > ``-v``."""
    if trace:
        return TRACE
    if debug:
        return logging.DEBUG
    if log:
        if log.isdigit():
            return int(log)
        level = logging.getLevelName(log.upper())
        if not isinstance(level, int):
            raise ValueError(f"Unknown log level: {log}")
        return level
    return LEVELS[min(verbose, len(LEVELS) - 1)]


def set_level(level: int) -> None:
    """Apply the log level, at trace level also for http libraries."""
    if not any(isinstance(h, RichHandler) for h in logger.handlers):
        logger.addHandler(RichHandler(show_path=False, show_time=False))
    logger.setLevel(level)
    for name in ("httpx", "httpcore", "py_oidc_auth_client"):
        logging.getLogger(name).setLevel(logging.DEBUG if level <= TRACE else logging.WARNING)
