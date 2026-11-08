from __future__ import annotations

import json
from typing import Any


def _payload(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value
