"""Google Calendar production adapter (OAuth2 + Calendar API v3).

Stdlib only — no google-api client package. Soft-confirm write path is unchanged:
ActionGateway.propose → Android/WhatsApp Accept → execute → adapter.create.

Default ``live=False`` shapes API payloads and updates the local mirror store
without calling Google. Operator sets ``CALENDAR_LIVE=1`` (or config live: true)
after OAuth secrets are filled.

Never commit real client secrets or refresh tokens — use config/production/calendar.env.example.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
from uuid import uuid4

from capabilities.calendar.store import CalendarEvent, CalendarStore

TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"

# Operator-facing OAuth scopes (read + write primary calendar).
DEFAULT_SCOPES = (
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
)

HttpTransport = Callable[[str, str, dict[str, str], Optional[bytes]], dict[str, Any]]


class GoogleCalendarError(RuntimeError):
    """Raised when Google OAuth or Calendar API calls fail."""


@dataclass
class GoogleCalendarConfig:
    """Production Google Calendar settings (no secrets in-repo)."""

    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    access_token: str = ""
    token_uri: str = TOKEN_URL
    calendar_id: str = "primary"
    timezone: str = "UTC"
    scopes: tuple[str, ...] = DEFAULT_SCOPES
    live: bool = False
    api_base: str = CALENDAR_API_BASE
    # Optional path to a JSON token file written by the operator OAuth helper.
    token_file: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize without secrets (for artifacts / diagnostics)."""
        return {
            "calendar_id": self.calendar_id,
            "timezone": self.timezone,
            "scopes": list(self.scopes),
            "live": self.live,
            "api_base": self.api_base,
            "token_uri": self.token_uri,
            "token_file": self.token_file,
            "client_id_set": bool(self.client_id),
            "client_secret_set": bool(self.client_secret),
            "refresh_token_set": bool(self.refresh_token),
            "access_token_set": bool(self.access_token),
            "configured": self.configured,
        }


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_google_calendar_config(
    *,
    env: Mapping[str, str] | None = None,
    config_path: Path | str | None = None,
) -> GoogleCalendarConfig:
    """Load production config from example YAML/JSON + environment secrets.

    Precedence: environment overrides file values. Secrets never required in file.
    """
    environ = dict(os.environ if env is None else env)
    data: dict[str, Any] = {}
    if config_path is not None:
        path = Path(config_path)
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if path.suffix.lower() in {".yaml", ".yml"}:
                data = _parse_simple_yaml_mapping(text)
            else:
                data = json.loads(text)

    google = data.get("google") if isinstance(data.get("google"), dict) else data
    if not isinstance(google, dict):
        google = {}

    # Nested google.live wins; else top-level production JSON "live"
    # (docs/calendar-production.md — operator sets "live": true on the profile).
    if "live" in google:
        live_default = bool(google.get("live"))
    elif "live" in data:
        live_default = bool(data.get("live"))
    else:
        live_default = False
    live = _env_bool("CALENDAR_LIVE", live_default) if env is None else (
        str(environ.get("CALENDAR_LIVE", str(live_default))).lower()
        in {"1", "true", "yes", "on"}
    )

    scopes_raw = google.get("scopes") or list(DEFAULT_SCOPES)
    if isinstance(scopes_raw, str):
        scopes = tuple(s.strip() for s in scopes_raw.split() if s.strip())
    else:
        scopes = tuple(str(s) for s in scopes_raw)

    return GoogleCalendarConfig(
        client_id=str(
            environ.get("GOOGLE_CALENDAR_CLIENT_ID")
            or google.get("client_id")
            or ""
        ),
        client_secret=str(
            environ.get("GOOGLE_CALENDAR_CLIENT_SECRET")
            or google.get("client_secret")
            or ""
        ),
        refresh_token=str(
            environ.get("GOOGLE_CALENDAR_REFRESH_TOKEN")
            or google.get("refresh_token")
            or ""
        ),
        access_token=str(
            environ.get("GOOGLE_CALENDAR_ACCESS_TOKEN")
            or google.get("access_token")
            or ""
        ),
        token_uri=str(google.get("token_uri") or TOKEN_URL),
        calendar_id=str(
            environ.get("GOOGLE_CALENDAR_ID")
            or google.get("calendar_id")
            or "primary"
        ),
        timezone=str(
            environ.get("GOOGLE_CALENDAR_TIMEZONE")
            or google.get("timezone")
            or "UTC"
        ),
        scopes=scopes,
        live=live,
        api_base=str(google.get("api_base") or CALENDAR_API_BASE),
        token_file=str(
            environ.get("GOOGLE_CALENDAR_TOKEN_FILE")
            or google.get("token_file")
            or ""
        ),
    )


def _parse_simple_yaml_mapping(text: str) -> dict[str, Any]:
    """Minimal YAML subset parser for our example templates (stdlib only).

    Supports nested maps via indentation, lists of scalars, and `#` comments.
    Not a general YAML implementation — enough for config/*.example.yaml.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    pending_list_key: str | None = None
    pending_list_indent = -1

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]

        if line.startswith("- "):
            if pending_list_key is None:
                continue
            value = _yaml_scalar(line[2:].strip())
            bucket = current.setdefault(pending_list_key, [])
            if not isinstance(bucket, list):
                bucket = []
                current[pending_list_key] = bucket
            bucket.append(value)
            continue

        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        pending_list_key = None
        if rest == "":
            nested: dict[str, Any] = {}
            current[key] = nested
            stack.append((indent, nested))
            pending_list_key = None
            pending_list_indent = indent
            # Next list items may attach to this key if they appear as `-` under parent.
            # For `scopes:` followed by `- item`, we need the key on current, not nested.
            # Re-interpret empty value as list-capable placeholder:
            current[key] = []
            pending_list_key = key
            # Also allow nested map if next line is `key: value` at greater indent —
            # detect by replacing list with dict when a mapping child appears.
            stack.append((indent, current))  # keep parent for list
            # Fix: use a dedicated container
            continue
        current[key] = _yaml_scalar(rest)

    # Second pass: recover nested maps that were incorrectly set to [].
    # Re-parse with a slightly smarter approach.
    return _parse_simple_yaml_mapping_v2(text)


def _parse_simple_yaml_mapping_v2(text: str) -> dict[str, Any]:
    """Indent-aware YAML subset → nested dicts/lists."""
    root: dict[str, Any] = {}
    # stack entries: (indent, container)
    stack: list[tuple[int, Any]] = [(-1, root)]
    last_key_at_indent: dict[int, str] = {}

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()

        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        container = stack[-1][1]

        if line.startswith("- "):
            item = _yaml_scalar(line[2:].strip())
            if isinstance(container, list):
                container.append(item)
            continue

        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        rest = rest.strip()
        last_key_at_indent[indent] = key

        if rest == "":
            # Peek: decide list vs map from following structure — default map;
            # if next non-empty sibling lines start with `-`, use list.
            # We create a map first; list conversion happens when `-` is seen
            # under this key by checking parent.
            # Simpler: create empty dict; if we later see `-` at greater indent
            # while current top is this dict and it's empty, convert parent value to list.
            nested: Any = {}
            if isinstance(container, dict):
                container[key] = nested
            stack.append((indent, nested))
            continue

        if isinstance(container, dict):
            container[key] = _yaml_scalar(rest)

    # Convert empty-dict values that only received list items via a fixup scan.
    # Re-scan for list keys: lines like `scopes:` followed by indented `-`.
    return _yaml_apply_list_keys(text, root)


def _yaml_apply_list_keys(text: str, root: dict[str, Any]) -> dict[str, Any]:
    """Fix keys whose children were list items (`-`) into real lists."""
    lines = text.splitlines()
    list_paths: list[tuple[str, ...]] = []
    # Track path by indent
    path_at_indent: dict[int, tuple[str, ...]] = {}
    for raw_line in lines:
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        # Drop deeper paths
        for i in list(path_at_indent):
            if i >= indent:
                del path_at_indent[i]
        if line.startswith("- "):
            parent_indent = max((i for i in path_at_indent if i < indent), default=None)
            if parent_indent is not None:
                list_paths.append(path_at_indent[parent_indent])
            continue
        if ":" not in line:
            continue
        key = line.split(":", 1)[0].strip()
        parent = ()
        parent_inds = [i for i in path_at_indent if i < indent]
        if parent_inds:
            parent = path_at_indent[max(parent_inds)]
        path_at_indent[indent] = parent + (key,)

    for path in list_paths:
        node: Any = root
        for part in path[:-1]:
            if not isinstance(node, dict) or part not in node:
                break
            node = node[part]
        else:
            leaf = path[-1]
            if isinstance(node, dict):
                existing = node.get(leaf)
                if isinstance(existing, dict) and not existing:
                    node[leaf] = []
                elif existing is None:
                    node[leaf] = []

    # Populate lists from text
    path_at_indent = {}
    for raw_line in lines:
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        line = raw_line.strip()
        for i in list(path_at_indent):
            if i >= indent:
                del path_at_indent[i]
        if line.startswith("- "):
            parent_indent = max((i for i in path_at_indent if i < indent), default=None)
            if parent_indent is None:
                continue
            path = path_at_indent[parent_indent]
            node: Any = root
            for part in path[:-1]:
                node = node[part]
            leaf = path[-1]
            if not isinstance(node.get(leaf), list):
                node[leaf] = []
            node[leaf].append(_yaml_scalar(line[2:].strip()))
            continue
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key = key.strip()
        parent = ()
        parent_inds = [i for i in path_at_indent if i < indent]
        if parent_inds:
            parent = path_at_indent[max(parent_inds)]
        path_at_indent[indent] = parent + (key,)
        if rest.strip():
            node = root
            for part in path_at_indent[indent][:-1]:
                node = node[part]
            if isinstance(node, dict):
                node[key] = _yaml_scalar(rest.strip())

    return root


def _yaml_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "Null", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def default_http_transport(
    method: str,
    url: str,
    headers: dict[str, str],
    body: Optional[bytes],
) -> dict[str, Any]:
    """Stdlib HTTPS transport for Google APIs."""
    req = urllib.request.Request(url, data=body, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            if not raw.strip():
                return {"status": resp.status}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GoogleCalendarError(f"http_{exc.code}:{detail}") from exc
    except urllib.error.URLError as exc:
        raise GoogleCalendarError(f"network:{exc.reason}") from exc


@dataclass
class GoogleCalendarAdapter:
    """Production Google Calendar adapter with soft-confirm-safe counters.

    create_count stays 0 until ActionGateway calls create() after Accept.
    Conflict-aware suggestions use the attached CalendarStore mirror — call
    ``sync_window`` (or seed from fixtures in tests) before propose.
    """

    config: GoogleCalendarConfig = field(default_factory=GoogleCalendarConfig)
    store: CalendarStore = field(default_factory=CalendarStore)
    transport: HttpTransport = field(default=default_http_transport, repr=False)
    create_count: int = 0
    modify_count: int = 0
    cancel_count: int = 0
    http_calls: list[dict[str, Any]] = field(default_factory=list)
    _access_token: str = field(default="", repr=False)
    _token_expires_at: Optional[datetime] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.config.access_token:
            self._access_token = self.config.access_token
        if self.config.token_file:
            self._load_token_file(self.config.token_file)

    def attach_store(self, store: CalendarStore) -> None:
        if self.store is store:
            return
        if self.store.events and not store.events:
            for evt in self.store.list_all():
                store.events[evt.id] = evt
        elif self.store.events and store.events:
            for evt in self.store.list_all():
                if evt.id not in store.events:
                    store.events[evt.id] = evt
        self.store = store

    @property
    def events(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.store.list_all()]

    @property
    def provider(self) -> str:
        return "google"

    @property
    def live(self) -> bool:
        return bool(self.config.live)

    def create(self, event: dict[str, Any]) -> dict[str, Any]:
        """Write path after soft confirm — increments create_count once."""
        self.create_count += 1
        payload = dict(event)
        body = self._event_body_from_payload(payload)
        google_id: str | None = None

        if self.config.live:
            self._ensure_access_token()
            url = (
                f"{self.config.api_base.rstrip('/')}/calendars/"
                f"{urllib.parse.quote(self.config.calendar_id)}/events"
            )
            resp = self._request("POST", url, body)
            google_id = str(resp.get("id") or "")
            payload["meta"] = {
                **dict(payload.get("meta") or {}),
                "google_event_id": google_id,
                "html_link": resp.get("htmlLink"),
                "provider": "google",
            }
        else:
            # Dry-run: record shaped request; no network.
            self.http_calls.append(
                {
                    "method": "POST",
                    "path": f"/calendars/{self.config.calendar_id}/events",
                    "body": body,
                    "live": False,
                }
            )
            google_id = f"google-dry-{self.create_count}-{uuid4().hex[:8]}"
            payload["meta"] = {
                **dict(payload.get("meta") or {}),
                "google_event_id": google_id,
                "provider": "google",
                "dry_run": True,
            }

        if google_id:
            payload.setdefault("id", google_id)
        stored = self.store.upsert_from_payload(payload)
        result = stored.to_dict()
        result["provider"] = "google"
        result["live"] = self.config.live
        return result

    def modify(self, event_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        self.modify_count += 1
        existing = self.store.get(event_id)
        merged = existing.to_dict() if existing else {"id": event_id}
        merged.update({k: v for k, v in patch.items() if v is not None})
        body = self._event_body_from_payload(merged)
        google_id = str(
            (merged.get("meta") or {}).get("google_event_id") or event_id
        )

        if self.config.live:
            self._ensure_access_token()
            url = (
                f"{self.config.api_base.rstrip('/')}/calendars/"
                f"{urllib.parse.quote(self.config.calendar_id)}/events/"
                f"{urllib.parse.quote(google_id)}"
            )
            resp = self._request("PATCH", url, body)
            merged["meta"] = {
                **dict(merged.get("meta") or {}),
                "google_event_id": resp.get("id") or google_id,
                "html_link": resp.get("htmlLink"),
                "provider": "google",
            }
        else:
            self.http_calls.append(
                {
                    "method": "PATCH",
                    "path": f"/calendars/{self.config.calendar_id}/events/{google_id}",
                    "body": body,
                    "live": False,
                }
            )
            merged["meta"] = {
                **dict(merged.get("meta") or {}),
                "google_event_id": google_id,
                "provider": "google",
                "dry_run": True,
            }

        updated = self.store.modify(event_id, merged)
        result = updated.to_dict()
        result["provider"] = "google"
        result["live"] = self.config.live
        return result

    def cancel(self, event_id: str) -> bool:
        self.cancel_count += 1
        existing = self.store.get(event_id)
        google_id = event_id
        if existing and existing.meta.get("google_event_id"):
            google_id = str(existing.meta["google_event_id"])

        if self.config.live:
            self._ensure_access_token()
            url = (
                f"{self.config.api_base.rstrip('/')}/calendars/"
                f"{urllib.parse.quote(self.config.calendar_id)}/events/"
                f"{urllib.parse.quote(google_id)}"
            )
            self._request("DELETE", url, None)
        else:
            self.http_calls.append(
                {
                    "method": "DELETE",
                    "path": f"/calendars/{self.config.calendar_id}/events/{google_id}",
                    "body": None,
                    "live": False,
                }
            )
        return self.store.cancel(event_id)

    def sync_window(
        self,
        *,
        time_min: datetime,
        time_max: datetime,
    ) -> list[CalendarEvent]:
        """Fetch busy events into the local store for conflict-aware suggestions.

        In dry-run / non-live mode returns the current store window (fixtures).
        """
        if not self.config.live:
            return self.store.list_between(time_min, time_max)

        self._ensure_access_token()
        params = urllib.parse.urlencode(
            {
                "timeMin": _to_rfc3339(time_min),
                "timeMax": _to_rfc3339(time_max),
                "singleEvents": "true",
                "orderBy": "startTime",
            }
        )
        url = (
            f"{self.config.api_base.rstrip('/')}/calendars/"
            f"{urllib.parse.quote(self.config.calendar_id)}/events?{params}"
        )
        resp = self._request("GET", url, None)
        synced: list[CalendarEvent] = []
        for item in resp.get("items") or []:
            evt = _event_from_google_item(item, default_tz=self.config.timezone)
            self.store.events[evt.id] = evt
            synced.append(evt)
        return synced

    def reset(self) -> None:
        self.store.clear()
        self.create_count = 0
        self.modify_count = 0
        self.cancel_count = 0
        self.http_calls.clear()
        self._access_token = self.config.access_token or ""
        self._token_expires_at = None

    def _event_body_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        start = payload.get("start")
        end = payload.get("end")
        tz = str(payload.get("timezone") or self.config.timezone or "UTC")
        body: dict[str, Any] = {
            "summary": str(payload.get("title") or payload.get("summary") or ""),
            "start": _google_date_field(start, tz),
            "end": _google_date_field(end, tz),
        }
        if payload.get("location"):
            body["location"] = str(payload["location"])
        if payload.get("description"):
            body["description"] = str(payload["description"])
        return body

    def _ensure_access_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._access_token and (
            self._token_expires_at is None or now < self._token_expires_at
        ):
            return self._access_token
        if not self.config.configured and not self._access_token:
            raise GoogleCalendarError(
                "missing_oauth_credentials: set GOOGLE_CALENDAR_CLIENT_ID/"
                "CLIENT_SECRET/REFRESH_TOKEN (see config/production/calendar.env.example)"
            )
        if self._access_token and not self.config.refresh_token:
            return self._access_token
        token = self._refresh_access_token()
        self._access_token = token
        return token

    def _refresh_access_token(self) -> str:
        form = urllib.parse.urlencode(
            {
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "refresh_token": self.config.refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = self.transport("POST", self.config.token_uri, headers, form)
        self.http_calls.append(
            {"method": "POST", "path": self.config.token_uri, "live": True, "kind": "token"}
        )
        access = str(resp.get("access_token") or "")
        if not access:
            raise GoogleCalendarError(f"token_refresh_failed:{resp!r}")
        expires_in = int(resp.get("expires_in") or 3600)
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=max(60, expires_in - 60)
        )
        return access

    def _request(
        self,
        method: str,
        url: str,
        body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
        raw: Optional[bytes] = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            raw = json.dumps(body).encode("utf-8")
        self.http_calls.append(
            {"method": method, "path": url, "body": body, "live": True}
        )
        return self.transport(method, url, headers, raw)

    def _load_token_file(self, path: str) -> None:
        p = Path(path)
        if not p.is_file():
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("refresh_token"):
            self.config.refresh_token = str(data["refresh_token"])
        if data.get("access_token"):
            self._access_token = str(data["access_token"])
            self.config.access_token = self._access_token
        if data.get("client_id"):
            self.config.client_id = str(data["client_id"])
        if data.get("client_secret"):
            self.config.client_secret = str(data["client_secret"])


def _to_rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _google_date_field(value: Any, tz: str) -> dict[str, str]:
    if value is None or value == "":
        raise GoogleCalendarError("event_missing_start_or_end")
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        return {"dateTime": dt.isoformat(), "timeZone": tz}
    return {"dateTime": dt.isoformat(), "timeZone": tz}


def _event_from_google_item(item: dict[str, Any], *, default_tz: str) -> CalendarEvent:
    start_raw = item.get("start") or {}
    end_raw = item.get("end") or {}
    start_s = start_raw.get("dateTime") or start_raw.get("date")
    end_s = end_raw.get("dateTime") or end_raw.get("date")
    if not start_s or not end_s:
        raise GoogleCalendarError("google_event_missing_times")
    start = datetime.fromisoformat(str(start_s).replace("Z", "+00:00"))
    end = datetime.fromisoformat(str(end_s).replace("Z", "+00:00"))
    # All-day dates are date-only; treat as midnight→next day if needed.
    if "T" not in str(start_s) and end.date() == start.date():
        end = start + timedelta(days=1)
    gid = str(item.get("id") or f"google-{uuid4().hex[:12]}")
    return CalendarEvent(
        id=gid,
        title=str(item.get("summary") or ""),
        start=start,
        end=end,
        timezone=str(
            start_raw.get("timeZone") or end_raw.get("timeZone") or default_tz
        ),
        location=str(item.get("location") or ""),
        meta={
            "google_event_id": gid,
            "html_link": item.get("htmlLink"),
            "provider": "google",
        },
    )
