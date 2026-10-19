"""Credential failover with shared per-project quotas, never key-based quotas."""
from collections import defaultdict, deque
from dataclasses import dataclass, field
from time import monotonic

from pydantic import SecretStr


@dataclass
class Credential:
    slot: int
    secret: str = field(repr=False)
    project: str
    disabled: bool = False


class GeminiKeyPool:
    def __init__(self, credentials, *, rpm=15):
        self.credentials = []
        seen = {}
        for index, (secret, project) in enumerate(credentials, 1):
            key = (secret.get_secret_value() if isinstance(secret, SecretStr) else secret or '').strip()
            if not key:
                continue
            group = (project or '').strip() or 'unverified-project'
            if key in seen:
                if seen[key] != group:
                    raise ValueError('Duplicate Gemini key has conflicting project identifiers')
                continue
            seen[key] = group
            self.credentials.append(Credential(index, key, group))
        self.rpm = rpm
        self._cursor = 0
        self._used = defaultdict(deque)
        self._cooldown = defaultdict(float)

    def available(self, *, excluded=(), reserve=False):
        now = monotonic()
        for offset in range(len(self.credentials)):
            index = (self._cursor + offset) % len(self.credentials)
            credential = self.credentials[index]
            group = credential.project
            used = self._used[group]
            while used and used[0] <= now - 60:
                used.popleft()
            if (credential.slot in excluded or credential.disabled
                    or self._cooldown[group] > now or len(used) >= self.rpm):
                continue
            if reserve:
                used.append(now)
                self._cursor = (index + 1) % len(self.credentials)
            return credential
        return None

    def rate_limited(self, credential, seconds=60):
        self._cooldown[credential.project] = max(self._cooldown[credential.project], monotonic() + seconds)

    def disable(self, credential):
        credential.disabled = True

    @property
    def configured(self):
        return bool(self.credentials)
