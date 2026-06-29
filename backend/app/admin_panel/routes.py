from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_panel.forms import FormError, field_specs, parse_form_data
from app.admin_panel.registry import AdminTable, all_tables, format_cell, get_table
from app.core.errors import AppError
from app.db.session import get_session
from app.models.order import Order
from app.models.redeem import RedeemRecord
from app.models.settings import StrategySettings
from app.models.user import User
from app.models.wallet import WalletCredential
from app.services.auth import (
    AUTH_COOKIE_NAME,
    authenticate_user,
    clear_auth_cookie,
    create_access_token,
    decode_access_token,
    set_auth_cookie,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/admin_panel/templates")
templates.env.filters["format_cell"] = format_cell
templates.env.filters["field_label"] = lambda value: str(value).replace("_", " ").title()
templates.env.filters["badge_class"] = lambda value: _badge_class(value)
MAX_LIMIT = 500
DEFAULT_LIMIT = 100


@router.get("/admin-panel/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return _template(request, "admin_panel/login.html", {"title": "Admin Login"})


@router.post("/admin-panel/login")
async def login(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    form = await request.form()
    username = str(form.get("username") or "")
    password = str(form.get("password") or "")
    try:
        user = await authenticate_user(session, username, password)
    except AppError:
        return _template(
            request,
            "admin_panel/login.html",
            {"title": "Admin Login", "error": "Invalid username or password."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if user.role not in ("admin", "super_user"):
        return _error(request, 403, "Admin access is required.")
    response = RedirectResponse("/admin-panel", status_code=status.HTTP_303_SEE_OTHER)
    set_auth_cookie(response, create_access_token(user))
    return response


@router.post("/admin-panel/logout")
async def logout() -> Response:
    response = RedirectResponse("/admin-panel/login", status_code=status.HTTP_303_SEE_OTHER)
    clear_auth_cookie(response)
    return response


@router.get("/admin-panel", response_class=HTMLResponse)
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    admin = await _require_admin(request, session)
    if isinstance(admin, Response):
        return admin
    stats = {
        "total_users": await _count(session, User),
        "active_users": await _count(session, User, User.is_active.is_(True)),
        "configured_wallets": await _count(session, WalletCredential, WalletCredential.is_configured.is_(True)),
        "real_trading_enabled": await _count(session, StrategySettings, StrategySettings.trading_enabled.is_(True)),
        "total_orders": await _count(session, Order),
        "failed_orders": await _count(session, Order, Order.status.in_(("failed", "error", "rejected"))),
        "failed_redeems": await _count(session, RedeemRecord, RedeemRecord.status.in_(("failed", "error"))),
    }
    return _template(request, "admin_panel/dashboard.html", {"admin": admin, "stats": stats, "title": "Dashboard"})


@router.get("/admin-panel/tables", response_class=HTMLResponse)
async def table_list(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    admin = await _require_admin(request, session)
    if isinstance(admin, Response):
        return admin
    return _template(
        request,
        "admin_panel/table_list.html",
        {"admin": admin, "tables": all_tables(), "title": "Tables"},
    )


@router.get("/admin-panel/tables/{table_name}", response_class=HTMLResponse)
async def table_detail(
    table_name: str,
    request: Request,
    page: int = 1,
    limit: int = DEFAULT_LIMIT,
    session: AsyncSession = Depends(get_session),
) -> Response:
    admin = await _require_admin(request, session)
    if isinstance(admin, Response):
        return admin
    table = _table_or_error(request, table_name)
    if isinstance(table, Response):
        return table
    safe_limit = min(max(limit, 1), MAX_LIMIT)
    safe_page = max(page, 1)
    result = await session.execute(
        select(table.model).order_by(table.model.id).offset((safe_page - 1) * safe_limit).limit(safe_limit)
    )
    rows = [table.public_row(row) for row in result.scalars().all()]
    return _template(
        request,
        "admin_panel/table_detail.html",
        {
            "admin": admin,
            "table": table,
            "fields": table.list_display_fields(),
            "rows": rows,
            "page": safe_page,
            "limit": safe_limit,
            "title": table.label,
        },
    )


@router.get("/admin-panel/tables/{table_name}/new", response_class=HTMLResponse)
async def new_object_page(table_name: str, request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    admin = await _require_admin(request, session)
    if isinstance(admin, Response):
        return admin
    table = _table_or_error(request, table_name)
    if isinstance(table, Response):
        return table
    if not table.can_create(admin):
        return _error(request, 403, "This table does not allow creating records.")
    return _form(request, admin, table, creating=True)


@router.post("/admin-panel/tables/{table_name}/new")
async def create_object(table_name: str, request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    admin = await _require_admin(request, session)
    if isinstance(admin, Response):
        return admin
    table = _table_or_error(request, table_name)
    if isinstance(table, Response):
        return table
    if not table.can_create(admin):
        return _error(request, 403, "This table does not allow creating records.")
    form = dict(await request.form())
    try:
        obj = table.model(**parse_form_data(table, form, creating=True))
        session.add(obj)
        await session.commit()
        await session.refresh(obj)
    except (FormError, SQLAlchemyError) as exc:
        await session.rollback()
        return _form(request, admin, table, creating=True, error=str(exc), values=form)
    return RedirectResponse(f"/admin-panel/tables/{table.name}/{obj.id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/admin-panel/tables/{table_name}/{object_id}", response_class=HTMLResponse)
async def object_detail(
    table_name: str,
    object_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    admin = await _require_admin(request, session)
    if isinstance(admin, Response):
        return admin
    table = _table_or_error(request, table_name)
    if isinstance(table, Response):
        return table
    obj = await session.get(table.model, object_id)
    if obj is None:
        return _error(request, 404, "Object not found.")
    return _template(
        request,
        "admin_panel/object_detail.html",
        {
            "admin": admin,
            "table": table,
            "row": table.public_row(obj, detail=True),
            "object_id": object_id,
            "title": f"{table.label} #{object_id}",
        },
    )


@router.get("/admin-panel/tables/{table_name}/{object_id}/edit", response_class=HTMLResponse)
async def edit_object_page(
    table_name: str,
    object_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    admin = await _require_admin(request, session)
    if isinstance(admin, Response):
        return admin
    table = _table_or_error(request, table_name)
    if isinstance(table, Response):
        return table
    if not table.can_edit(admin):
        return _error(request, 403, "This table is read-only.")
    obj = await session.get(table.model, object_id)
    if obj is None:
        return _error(request, 404, "Object not found.")
    values = {field: getattr(obj, field, "") for field in table.form_fields(creating=False)}
    values.pop("password", None)
    return _form(request, admin, table, creating=False, object_id=object_id, values=values)


@router.post("/admin-panel/tables/{table_name}/{object_id}/edit")
async def update_object(
    table_name: str,
    object_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    admin = await _require_admin(request, session)
    if isinstance(admin, Response):
        return admin
    table = _table_or_error(request, table_name)
    if isinstance(table, Response):
        return table
    if not table.can_edit(admin):
        return _error(request, 403, "This table is read-only.")
    obj = await session.get(table.model, object_id)
    if obj is None:
        return _error(request, 404, "Object not found.")
    form = dict(await request.form())
    try:
        for key, value in parse_form_data(table, form, creating=False).items():
            setattr(obj, key, value)
        await session.commit()
    except (FormError, SQLAlchemyError) as exc:
        await session.rollback()
        return _form(request, admin, table, creating=False, object_id=object_id, error=str(exc), values=form)
    return RedirectResponse(f"/admin-panel/tables/{table.name}/{object_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin-panel/tables/{table_name}/{object_id}/delete")
async def delete_object(
    table_name: str,
    object_id: int,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    admin = await _require_admin(request, session)
    if isinstance(admin, Response):
        return admin
    table = _table_or_error(request, table_name)
    if isinstance(table, Response):
        return table
    if not table.can_delete(admin):
        return _error(request, 403, "Deletion is disabled for this table.")
    if table.name == "users" and object_id == admin.id:
        return _error(request, 403, "You cannot delete your own admin user.")
    obj = await session.get(table.model, object_id)
    if obj is None:
        return _error(request, 404, "Object not found.")
    await session.delete(obj)
    await session.commit()
    return RedirectResponse(f"/admin-panel/tables/{table.name}", status_code=status.HTTP_303_SEE_OTHER)


async def _require_admin(request: Request, session: AsyncSession) -> User | Response:
    token = request.cookies.get(AUTH_COOKIE_NAME)
    if not token:
        return RedirectResponse("/admin-panel/login", status_code=status.HTTP_303_SEE_OTHER)
    try:
        payload = decode_access_token(token)
        user = await session.get(User, int(payload["sub"]))
    except (AppError, KeyError, TypeError, ValueError):
        return RedirectResponse("/admin-panel/login", status_code=status.HTTP_303_SEE_OTHER)
    if user is None or not user.is_active:
        return RedirectResponse("/admin-panel/login", status_code=status.HTTP_303_SEE_OTHER)
    if user.role not in ("admin", "super_user"):
        return _error(request, 403, "Admin access is required.")
    return user


async def _count(session: AsyncSession, model: type[Any], *conditions: Any) -> int:
    statement = select(func.count()).select_from(model)
    if conditions:
        statement = statement.where(*conditions)
    return int(await session.scalar(statement) or 0)


def _table_or_error(request: Request, table_name: str) -> AdminTable | Response:
    table = get_table(table_name)
    if table is None:
        return _error(request, 404, "Table is not allowlisted.")
    return table


def _form(
    request: Request,
    admin: User,
    table: AdminTable,
    *,
    creating: bool,
    object_id: int | None = None,
    error: str | None = None,
    values: dict[str, Any] | None = None,
) -> HTMLResponse:
    return _template(
        request,
        "admin_panel/object_form.html",
        {
            "admin": admin,
            "table": table,
            "fields": field_specs(table, creating=creating),
            "creating": creating,
            "object_id": object_id,
            "error": error,
            "values": values or {},
            "title": f"{'New' if creating else 'Edit'} {table.label}",
        },
    )


def _error(request: Request, code: int, message: str) -> HTMLResponse:
    return _template(
        request,
        "admin_panel/error.html",
        {"title": str(code), "status_code": code, "message": message},
        status_code=code,
    )


def _template(request: Request, template: str, context: dict[str, Any], status_code: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request, template, context, status_code=status_code)


def _badge_class(value: Any) -> str:
    normalized = str(value).lower()
    if value is True or normalized in {"enabled", "active", "success", "filled", "complete", "completed", "super_user"}:
        return "badge positive"
    if value is False or normalized in {"disabled", "inactive", "failed", "error", "rejected", "kill", "blocked"}:
        return "badge negative"
    if normalized in {"admin", "real", "submitted", "pending", "open"}:
        return "badge warning"
    if normalized in {"viewer", "trader", "paper", "dry_run"}:
        return "badge neutral"
    return "badge neutral"
