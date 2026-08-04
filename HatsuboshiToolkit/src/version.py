import re
from pathlib import Path
from urllib.parse import urljoin

import requests

from src.config import APP_ID, CLIENT_SECRET_KEY, URL, VERSION


VERSION_STEP = 100
VERSION_PROBES = 20


def _version_is_available(version: int) -> bool:
    path = f"v2/pub/a/{APP_ID}/v/{version}/list/0"
    url = urljoin(URL, path)
    headers = {
        "Accept": f"application/x-protobuf,x-octo-app/{APP_ID}",
        "X-OCTO-KEY": CLIENT_SECRET_KEY,
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
    except requests.RequestException:
        return False
    return response.status_code == 200


def find_latest_version() -> int:
    current = int(VERSION)
    latest = current
    for offset in range(1, VERSION_PROBES + 1):
        candidate = current + offset * VERSION_STEP
        if _version_is_available(candidate):
            latest = candidate
    return latest


def update_config_version() -> int:
    current = int(VERSION)
    latest = find_latest_version()
    if latest == current:
        return latest

    config_path = Path(__file__).resolve().parents[1] / "config.ini"
    config_text = config_path.read_text(encoding="utf-8")
    config_text, replacements = re.subn(
        r"(?m)^(VERSION\s*=\s*)\d+(\s*)$",
        lambda match: f"{match.group(1)}{latest}{match.group(2)}",
        config_text,
        count=1,
    )
    if replacements != 1:
        raise RuntimeError(f"Could not update VERSION in {config_path}")

    config_path.write_text(config_text, encoding="utf-8")
    return latest
