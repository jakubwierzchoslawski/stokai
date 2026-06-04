"""
data_providers.credentials_resolver — Runtime credential resolution.

Resolves a vault-reference string into the actual secret value.
Supported schemes:
  env:<ENV_VAR_NAME>  — reads os.environ[ENV_VAR_NAME]

Design decisions (PLAN-F-028, REQ-N-007):
  - Only os.environ is used — no Azure SDK, no cloud-specific imports.
  - The resolved secret is NEVER logged at any level.
  - The function is pure (no I/O side effects other than reading os.environ).
  - Raises ConfigurationError (not KeyError) so callers have a consistent
    exception type to catch without leaking the missing var name into logs.
"""
from __future__ import annotations

import os
import re

_CREDENTIALS_REF_RE = re.compile(r"^(env|vault):([A-Z0-9_]+)$")


class ConfigurationError(Exception):
    """Raised when a credentials_ref cannot be resolved (e.g. missing env var).

    The exception message includes the variable NAME but never the value.
    """


def resolve_credentials(ref: str) -> str:
    """Resolve a vault-reference string to the actual credential value.

    Supported schemes
    -----------------
    ``env:<ENV_VAR_NAME>``
        Read the value from ``os.environ``. Variable name must be uppercase
        alphanumeric + underscores only (``[A-Z0-9_]+``).

    Args:
        ref: A vault-reference string, e.g. ``"env:FINNHUB_API_KEY"``.

    Returns:
        The resolved credential string (never logged).

    Raises:
        ConfigurationError: If the scheme is unsupported or the env var is absent.
        ValueError: If ref does not match the expected format.

    Security:
        The returned value is NEVER logged. Callers must treat it as opaque.
    """
    match = _CREDENTIALS_REF_RE.match(ref)
    if not match:
        raise ValueError(
            f"credentials_ref {ref!r} does not match the required format "
            r"'^(env|vault):[A-Z0-9_]+$'."
        )

    scheme = match.group(1)
    key = match.group(2)

    if scheme == "env":
        value = os.environ.get(key)
        if value is None:
            # Log the var NAME only — never any sensitive value
            raise ConfigurationError(f"Missing env var: {key}")
        return value

    # scheme == "vault" — not yet implemented; raises to prevent silent failures
    raise ConfigurationError(
        f"Vault scheme is not yet implemented. Use 'env:{key}' instead."
    )
