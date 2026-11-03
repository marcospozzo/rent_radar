"""Sends alerts through Apprise, to whatever services alerts.yaml lists."""
from __future__ import annotations

from pathlib import Path

import apprise

from app.searches import AppriseService, SearchConfigError


SENDER_NAME = "Rent Radar"


def _service_url(service: AppriseService) -> str:
    path = Path(service.url_file)
    name = service.label or str(path)
    try:
        url = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise SearchConfigError(f"Apprise service '{name}': cannot read {path}: {exc.strerror}") from exc
    if not url:
        raise SearchConfigError(f"Apprise service '{name}': {path} is empty")
    return url


def build_notifier(services: list[AppriseService]) -> apprise.Apprise:
    """Fails with the service's name, never its URL: the URL holds a password."""
    # Apprise names the sender after the app id, "Apprise" by default; a `name=`
    # in the URL still takes precedence.
    notifier = apprise.Apprise(asset=apprise.AppriseAsset(app_id=SENDER_NAME))
    for service in services:
        if not notifier.add(_service_url(service)):
            raise SearchConfigError(
                f"Apprise service '{service.label or service.url_file}': "
                "the URL in that file is not one Apprise understands"
            )
    return notifier


def send(notifier: apprise.Apprise, title: str, body: str) -> bool:
    """True only if every service accepted the message."""
    return bool(notifier.notify(title=title, body=body, body_format=apprise.NotifyFormat.MARKDOWN))
