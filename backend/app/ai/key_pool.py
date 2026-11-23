"""Credential failover with shared per-project quotas, never key-based quotas."""
from collections import defaultdict, deque
from dataclasses import dataclass, field
from math import isfinite
from time import monotonic

from pydantic import SecretStr


def gemini_credentials(settings):
    return (
        (settings.gemini_api_key, settings.gemini_project_id),
        (settings.gemini_api_key_2, settings.gemini_project_id_2),
        (settings.gemini_api_key_3, settings.gemini_project_id_3),
    )


def retry_delay(value):
    try:
        seconds = float(value)
        return max(1, min(86400, seconds)) if isfinite(seconds) else 60
    except (TypeError, ValueError):
        return 60


def rejected_gemini_key(error):
    if not isinstance(error, dict) or not isinstance(error.get('details'), list):
        return False
    return any(
        isinstance(detail, dict)
        and detail.get('@type') == 'type.googleapis.com/google.rpc.ErrorInfo'
        and detail.get('reason') in ('API_KEY_INVALID', 'API_KEY_EXPIRED', 'API_KEY_SERVICE_BLOCKED')
        for detail in error['details']
    )


@dataclass
class Credential:
    slot: int
    secret: str = field(repr=False)
    project: str
    disabled: bool = False

    @property
    def cooldown_scope(self):
        # Confirmed projects share a cooldown. An unknown project can still have
        # a working key in another slot, so only cool the rejected slot down.
        return self.project or self.slot


class GeminiKeyPool:
    def __init__(self, credentials, *, rpm=15):
        self.credentials = []
        seen = {}
        for index, (secret, project) in enumerate(credentials, 1):
            key = (secret.get_secret_value() if isinstance(secret, SecretStr) else secret or '').strip()
            if not key:
                continue
            group = (project or '').strip()
            if key in seen:
                if seen[key] != group:
                    raise ValueError('Duplicate Gemini key has conflicting project identifiers')
                continue
            seen[key] = group
            self.credentials.append(Credential(index, key, group))
        self.rpm = rpm
        self._cursor = 0
        self._used = defaultdict(deque)
        self._cooldown = {}

    def available(self, *, excluded=(), reserve=False):
        now = monotonic()
        for offset in range(len(self.credentials)):
            index = (self._cursor + offset) % len(self.credentials)
            credential = self.credentials[index]
            group = credential.project or 'unverified-project'
            used = self._used[group]
            while used and used[0] <= now - 60:
                used.popleft()
            if (credential.slot in excluded or credential.disabled
                    or self.cooldown(credential, now=now)
                    or (self.rpm is not None and len(used) >= self.rpm)):
                continue
            if reserve:
                if self.rpm is not None:
                    used.append(now)
                self._cursor = (index + 1) % len(self.credentials)
            return credential
        return None

    def cooldown(self, credential, *, now=None):
        until, reason = self._cooldown.get(credential.cooldown_scope, (0, ''))
        remaining = until - (monotonic() if now is None else now)
        return (reason, remaining) if remaining > 0 else None

    def rate_limited(self, credential, seconds=60, *, reason='rate_limited'):
        scope = credential.cooldown_scope
        until = monotonic() + seconds
        if until >= self._cooldown.get(scope, (0, ''))[0]:
            self._cooldown[scope] = (until, reason)

    def disable(self, credential):
        credential.disabled = True

    @property
    def configured(self):
        return bool(self.credentials)
