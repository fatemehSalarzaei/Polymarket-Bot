from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.errors import AppError, build_error_response, code_from_detail
from app.main import app_error_handler, http_exception_handler


def test_error_mapping_builds_operator_friendly_payload() -> None:
    payload = build_error_response(
        "CURRENT_CHAINLINK_TICK_MISSING",
        technical_detail="no rows in chainlink_ticks",
        request_id="request-1",
    )

    assert payload.code == "CURRENT_CHAINLINK_TICK_MISSING"
    assert payload.title == "BTC live price is not available"
    assert payload.severity == "warning"
    assert payload.source == "rtds_chainlink"
    assert payload.technical_detail == "no rows in chainlink_ticks"
    assert payload.request_id == "request-1"
    assert payload.possible_causes
    assert payload.recovery_actions


def test_code_from_detail_accepts_legacy_string_codes() -> None:
    assert code_from_detail("UP_ORDERBOOK_MISSING") == "UP_ORDERBOOK_MISSING"
    assert code_from_detail({"code": "ORDERBOOK_PARSE_ERROR"}) == "ORDERBOOK_PARSE_ERROR"
    assert code_from_detail("something else") == "HTTP_ERROR"


def test_app_error_handler_returns_structured_error() -> None:
    test_app = FastAPI()
    test_app.add_exception_handler(AppError, app_error_handler)

    @test_app.get("/boom")
    async def boom() -> None:
        raise AppError("MARKET_WS_DISCONNECTED", technical_detail="socket closed", status_code=503)

    response = TestClient(test_app).get("/boom", headers={"x-request-id": "request-2"})

    assert response.status_code == 503
    assert response.json()["code"] == "MARKET_WS_DISCONNECTED"
    assert response.json()["request_id"] == "request-2"
    assert response.json()["technical_detail"] == "socket closed"


def test_http_exception_handler_maps_known_detail_code() -> None:
    test_app = FastAPI()
    test_app.add_exception_handler(HTTPException, http_exception_handler)

    @test_app.get("/boom")
    async def boom() -> None:
        raise HTTPException(status_code=404, detail="CURRENT_MARKET_MISSING")

    response = TestClient(test_app).get("/boom")

    assert response.status_code == 404
    assert response.json()["code"] == "CURRENT_MARKET_MISSING"
    assert response.json()["title"] == "Current market is not available"
