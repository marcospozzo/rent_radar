"""Sends alerts through Apprise, to whatever services alerts.yaml lists."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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


def _with_recipients(url: str, recipients: list[str], name: str) -> str:
    """The service's URL with `to` set to these addresses. Only the query changes:
    the credentials in the rest of the URL are kept exactly as written."""
    parts = urlsplit(url)
    if parts.scheme not in ("mailto", "mailtos"):
        raise SearchConfigError(
            f"Apprise service '{name}' is not an email service, so an alert cannot "
            "choose its recipients with `to`"
        )
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "to"]
    query.append(("to", ",".join(recipients)))
    return urlunsplit(parts._replace(query=urlencode(query)))


def build_notifier(services: list[AppriseService], recipients: list[str] | None = None) -> apprise.Apprise:
    """`recipients` replaces the URL's own `to`; without it the message goes where
    the URL says. Fails with the service's name, never its URL: the URL holds a password."""
    # Apprise names the sender after the app id, "Apprise" by default; a `name=`
    # in the URL still takes precedence.
    notifier = apprise.Apprise(asset=apprise.AppriseAsset(app_id=SENDER_NAME))
    for service in services:
        url = _service_url(service)
        if recipients:
            url = _with_recipients(url, recipients, service.label or service.url_file)
        if not notifier.add(url):
            raise SearchConfigError(
                f"Apprise service '{service.label or service.url_file}': "
                "the URL in that file is not one Apprise understands"
            )
    return notifier


def send(notifier: apprise.Apprise, title: str, body: str) -> bool:
    """True only if every service accepted the message."""
    return bool(notifier.notify(title=title, body=body, body_format=apprise.NotifyFormat.MARKDOWN))
