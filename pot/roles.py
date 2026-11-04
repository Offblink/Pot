"""Role definitions and templates — data/roles/<id>.json (spec §3.1, 裁决 6).

Human owns the privilege ground: tools / model / wip / canCreateCard, plus
update and delete. Planner may create roles, but only by deriving every
privilege from a human-made template; mission / name / canClaim labels are
its own. Files are read on every access so hand edits apply live.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pot.errors import PotError

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_CREATORS = ("human", "planner")
# Privilege keys a planner may never supply — rejected, never silently ignored.
_PRIVILEGED = ("tools", "model", "wip", "canCreateCard")


@dataclass(frozen=True)
class Actor:
    """Who is acting: a role inside a session. holder string = role:session."""

    role_id: str
    session_id: str

    @property
    def holder(self) -> str:
        return f"{self.role_id}:{self.session_id}"


@dataclass
class Role:
    # Field names mirror the JSON file format 1:1 (camelCase by spec decree;
    # ruff N815 ignored for this module in pyproject).
    id: str
    name: str = ""
    mission: str = ""
    tools: list[str] = field(default_factory=list)
    model: str | None = None
    wip: int = 2
    canClaim: list[str] | bool = field(default_factory=list)  # [] = every label; false = barred
    canCreateCard: bool = False
    template: str | None = None
    createdBy: str = "human"
    isTemplate: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            self.name = self.id

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "mission": self.mission,
            "tools": list(self.tools),
            "model": self.model,
            "wip": self.wip,
            "canClaim": self.canClaim,
            "canCreateCard": self.canCreateCard,
            "template": self.template,
            "createdBy": self.createdBy,
            "isTemplate": self.isTemplate,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Role:
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})


def _check(data: dict) -> dict:
    """Validate only the keys present; returns the dict for chaining."""
    rid = data.get("id")
    if rid is not None and (not isinstance(rid, str) or not _ID_RE.match(rid)):
        raise PotError("bad_id", repr(rid))
    for key in ("name", "mission", "model", "template"):
        if key in data and data[key] is not None and not isinstance(data[key], str):
            raise PotError("bad_value", key)
    if "tools" in data and (
        not isinstance(data["tools"], list) or not all(isinstance(t, str) for t in data["tools"])
    ):
        raise PotError("bad_value", "tools")
    if "wip" in data and (
        isinstance(data["wip"], bool) or not isinstance(data["wip"], int) or data["wip"] < 1
    ):
        raise PotError("bad_value", "wip")
    if "canClaim" in data:
        cc = data["canClaim"]
        if not (cc is False or (isinstance(cc, list) and all(isinstance(x, str) for x in cc))):
            raise PotError("bad_value", "canClaim")
    for key in ("canCreateCard", "isTemplate"):
        if key in data and not isinstance(data[key], bool):
            raise PotError("bad_value", key)
    if "createdBy" in data and data["createdBy"] not in _CREATORS:
        raise PotError("bad_value", "createdBy")
    return data


class RoleRepo:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, role_id: str) -> Path:
        return self.root / f"{role_id}.json"

    def _read(self, path: Path) -> Role:
        try:
            return Role.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            raise PotError("bad_role_file", f"{path.stem}: {exc}") from exc

    def get(self, role_id: str) -> Role:
        path = self._path(role_id)
        if not path.is_file():
            raise PotError("no_such_role", role_id)
        return self._read(path)

    def list(self, include_templates: bool = False) -> list[Role]:
        out = []
        for path in sorted(self.root.glob("*.json")):
            try:
                role = self._read(path)
            except PotError:
                continue  # a hand-edited broken file must not kill the board
            if role.isTemplate and not include_templates:
                continue
            out.append(role)
        return out

    def create(self, fields: dict, creator: str) -> Role:
        if creator not in _CREATORS:
            raise PotError("bad_value", f"creator={creator}")
        fields = _check(dict(fields))
        if "id" not in fields:
            raise PotError("bad_id", "missing")
        rid = fields["id"]
        if self._path(rid).is_file():
            raise PotError("id_exists", rid)
        if creator == "planner":
            if fields.get("isTemplate"):
                raise PotError("planner_no_privilege", "isTemplate")
            clash = [k for k in _PRIVILEGED if k in fields]
            if clash:
                raise PotError("planner_no_privilege", ", ".join(clash))
            tpl_id = fields.get("template")
            if not tpl_id:
                raise PotError("need_template", rid)
            tpl = self._template(tpl_id)
            fields["tools"] = list(tpl.tools)
            fields["model"] = tpl.model
            fields["wip"] = tpl.wip
            fields["canCreateCard"] = tpl.canCreateCard
        fields["createdBy"] = creator  # provenance comes from the actor, not the payload
        role = Role.from_dict(fields)
        self._write(role)
        return role

    def _template(self, template_id: str) -> Role:
        path = self._path(template_id)
        if not path.is_file():
            raise PotError("template_missing", template_id)
        role = self._read(path)
        if not role.isTemplate:
            raise PotError("not_template", template_id)
        return role

    def update(self, role_id: str, fields: dict, creator: str) -> Role:
        if creator != "human":
            raise PotError("human_only", f"update by {creator}")
        merged = self.get(role_id).to_dict()
        fields = dict(fields)
        if "id" in fields and fields.pop("id") != role_id:
            raise PotError("bad_id", role_id)
        fields.pop("createdBy", None)  # provenance is immutable
        merged.update(_check(fields))
        role = Role.from_dict(merged)
        self._write(role)
        return role

    def delete(self, role_id: str, creator: str) -> None:
        if creator != "human":
            raise PotError("human_only", f"delete by {creator}")
        path = self._path(role_id)
        if not path.is_file():
            raise PotError("no_such_role", role_id)
        path.unlink()

    def _write(self, role: Role) -> None:
        path = self._path(role.id)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(
            json.dumps(role.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        tmp.replace(path)
