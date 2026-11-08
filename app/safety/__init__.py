"""安全子层：注入隔离与 PII 脱敏。"""

from .injection import (  # noqa: F401
    InjectionFinding,
    restrict_tools,
    scan,
    wrap_untrusted,
)
from .redact import redact as redact_text, redact_deep  # noqa: F401
