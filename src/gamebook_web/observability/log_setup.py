from __future__ import annotations

import logging

_LOG_FMT = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s  %(message)s")


def setup_logging() -> None:
    """Attach stderr handlers to gamebook_web and classifier-eval loggers."""
    gw_log = logging.getLogger("gamebook_web")
    if not gw_log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_LOG_FMT)
        gw_log.addHandler(handler)
    gw_log.setLevel(logging.INFO)

    eval_log = logging.getLogger("gamebook.classifier.eval")
    if not eval_log.handlers:
        eval_handler = logging.StreamHandler()
        eval_handler.setFormatter(_LOG_FMT)
        eval_log.addHandler(eval_handler)
    eval_log.setLevel(logging.INFO)
    eval_log.propagate = False
