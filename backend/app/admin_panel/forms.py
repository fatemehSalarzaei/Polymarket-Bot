from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, Numeric
from sqlalchemy.inspection import inspect

from app.admin_panel.registry import AdminTable
from app.schemas.auth import USER_ROLE_OPTIONS, USER_ROLE_VALUES
from app.services.auth import hash_password


class FormError(ValueError):
    pass


def field_specs(table: AdminTable, *, creating: bool) -> list[dict[str, Any]]:
    columns = {column.key: column for column in inspect(table.model).columns}
    specs: list[dict[str, Any]] = []
    for field in table.form_fields(creating=creating):
        if field == "password":
            specs.append({"name": field, "label": "Password", "kind": "password", "required": creating})
            continue
        if field == "role":
            specs.append({"name": field, "label": "Role", "kind": "select", "required": True, "options": USER_ROLE_OPTIONS})
            continue
        column = columns[field]
        specs.append(
            {
                "name": field,
                "label": field.replace("_", " ").title(),
                "kind": _field_kind(column.type),
                "required": not column.nullable and column.default is None,
            }
        )
    return specs


def parse_form_data(table: AdminTable, form: dict[str, Any], *, creating: bool) -> dict[str, Any]:
    columns = {column.key: column for column in inspect(table.model).columns}
    updates: dict[str, Any] = {}
    for field in table.form_fields(creating=creating):
        if field == "password":
            password = str(form.get("password") or "")
            if password:
                updates["password_hash"] = hash_password(password)
            elif creating:
                raise FormError("Password is required.")
            continue

        column = columns[field]
        raw_value = form.get(field)
        if isinstance(column.type, Boolean):
            updates[field] = raw_value in ("on", "true", "True", "1", "yes")
            continue
        if field == "role":
            role = str(raw_value or "").strip()
            if role not in USER_ROLE_VALUES:
                raise FormError("Role must be one of the allowed values.")
            updates[field] = role
            continue
        if raw_value in (None, ""):
            if not column.nullable and column.default is None:
                raise FormError(f"{field.replace('_', ' ').title()} is required.")
            updates[field] = None
            continue
        updates[field] = _convert_value(raw_value, column.type, field)

    if table.name == "users":
        if "email" in updates and isinstance(updates["email"], str):
            updates["email"] = updates["email"].strip().lower()
        if "username" in updates and isinstance(updates["username"], str):
            updates["username"] = updates["username"].strip()
    return updates


def _convert_value(raw_value: Any, column_type: Any, field: str) -> Any:
    value = str(raw_value).strip()
    try:
        if isinstance(column_type, Integer):
            return int(value)
        if isinstance(column_type, Numeric):
            return Decimal(value)
        if isinstance(column_type, DateTime):
            return datetime.fromisoformat(value)
        if _field_kind(column_type) == "json":
            return json.loads(value)
    except (InvalidOperation, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise FormError(f"{field.replace('_', ' ').title()} has an invalid value.") from exc
    return value


def _field_kind(column_type: Any) -> str:
    if isinstance(column_type, Boolean):
        return "boolean"
    if isinstance(column_type, Integer):
        return "integer"
    if isinstance(column_type, Numeric):
        return "decimal"
    if isinstance(column_type, DateTime):
        return "datetime"
    if "JSON" in column_type.__class__.__name__.upper():
        return "json"
    return "string"
