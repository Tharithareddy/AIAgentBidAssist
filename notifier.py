"""Windows toast notifications for bid_monitor.py."""

import logging
import threading

from win10toast_click import ToastNotifier

logger = logging.getLogger("notifier")

_toaster = ToastNotifier()


def notify(title: str, message: str, duration: int = 10) -> None:
    """Show a Windows toast popup. Runs in a background thread so it never
    blocks the monitoring loop (win10toast's show_toast is blocking by default)."""
    logger.info("Notify: %s - %s", title, message)
    thread = threading.Thread(
        target=_toaster.show_toast,
        kwargs=dict(
            title=title,
            msg=message,
            duration=duration,
            threaded=False,
        ),
        daemon=True,
    )
    thread.start()
