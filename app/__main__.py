"""Start the server: `python -m app` (production and dev). Dev with auto-reload:
`python -m uvicorn app.main:app --reload --port 8000`.

PRODUCTION=True: HTTPS only with TLS_CERT_FILE/TLS_KEY_FILE; self-signed (unless TLS_ALLOW_SELF_SIGNED)
and expired certificates are refused; warns when fewer than 30 days remain.
"""
from __future__ import annotations

import logging
import ssl
import sys
import time
from pathlib import Path

import uvicorn

from app.config import ROOT, get_settings


def _setup_logging() -> None:
    (ROOT / "logs").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(ROOT / "logs" / "server.log", encoding="utf-8")):
        h.setFormatter(fmt)
        root.addHandler(h)


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else ROOT / path


def check_certificate(cert: Path, allow_self_signed: bool) -> list[str]:
    """Returns problems; logs names and expiry. Uses CPython's PEM decoder (no extra wheels)."""
    log = logging.getLogger("ra.tls")
    try:
        info = ssl._ssl._test_decode_cert(str(cert))  # noqa: SLF001 - stdlib, PEM only
    except Exception as e:
        return [f"cannot read certificate {cert}: {e}"]
    problems = []
    subject = dict(x[0] for x in info.get("subject", ()))
    issuer = dict(x[0] for x in info.get("issuer", ()))
    names = [v for k, v in info.get("subjectAltName", ()) if k == "DNS"]
    expires = ssl.cert_time_to_seconds(info["notAfter"])
    days = (expires - time.time()) / 86400
    log.info("Certificate: %s | issuer %s | valid names %s | expires %s (%.0f days)",
             subject.get("commonName"), issuer.get("commonName"), names or "-", info["notAfter"], days)
    if days <= 0:
        problems.append("certificate has expired")
    elif days < 30:
        log.warning("Certificate expires in %.0f days", days)
    if subject == issuer and not allow_self_signed:
        problems.append("certificate is self-signed (set TLS_ALLOW_SELF_SIGNED=True only on test machines)")
    return problems


def main() -> None:
    _setup_logging()
    s = get_settings()
    log = logging.getLogger("ra")
    kwargs: dict = {"host": s.HOST, "port": s.PORT, "log_config": None, "proxy_headers": False}
    if s.TLS_CERT_FILE and s.TLS_KEY_FILE:
        cert, key = _resolve(s.TLS_CERT_FILE), _resolve(s.TLS_KEY_FILE)
        problems = check_certificate(cert, s.TLS_ALLOW_SELF_SIGNED or not s.PRODUCTION)
        if problems and s.PRODUCTION:
            for p in problems:
                log.error("TLS: %s", p)
            sys.exit(2)
        kwargs.update(ssl_certfile=str(cert), ssl_keyfile=str(key))
        scheme = "https"
    elif s.PRODUCTION:
        log.error("PRODUCTION=True requires TLS_CERT_FILE and TLS_KEY_FILE")
        sys.exit(2)
    else:
        scheme = "http"
    log.info("Listening on %s://%s:%s", scheme, s.HOST, s.PORT)
    uvicorn.run("app.main:app", **kwargs)


if __name__ == "__main__":
    main()
