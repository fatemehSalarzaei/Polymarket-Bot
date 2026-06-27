from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.dashboard_broadcaster import dashboard_broadcaster

router = APIRouter()


@router.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket) -> None:
    await dashboard_broadcaster.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await dashboard_broadcaster.disconnect(websocket)

