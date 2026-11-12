"""WebSocket endpoint for real-time friend location sharing.

The browser cannot set an Authorization header on a WebSocket handshake, so the
Keycloak access token is passed as a ``?token=`` query parameter and verified
here. The verified Keycloak identity is mapped onto the local ``users`` row so
connections stay keyed by the same integer user id used everywhere else.
"""
import json
from collections import defaultdict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.database import AsyncSessionLocal
from app.core.security import provision_user, verify_token

router = APIRouter()

# In-memory location store: user_id -> {lat, lng, username, ts}
_locations: dict[int, dict] = {}

# Active connections grouped by user_id
_connections: dict[int, list[WebSocket]] = defaultdict(list)


async def _authenticate(token: str | None) -> int | None:
    """Resolve a Keycloak access token to a local user id, or None."""
    if not token:
        return None
    claims = await verify_token(token)
    if not claims:
        return None
    async with AsyncSessionLocal() as db:
        user = await provision_user(db, claims)
        return user.id


@router.websocket("/ws/location")
async def location_ws(ws: WebSocket):
    user_id = await _authenticate(ws.query_params.get("token"))

    if user_id is None:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await ws.accept()
    _connections[user_id].append(ws)

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)

            if msg.get("type") == "location":
                _locations[user_id] = {
                    "lat": msg["lat"],
                    "lng": msg["lng"],
                    "username": msg.get("username", ""),
                    "user_id": user_id,
                }

                # Broadcast to all connected clients (they filter by friend list)
                payload = json.dumps({
                    "type": "friend_location",
                    **_locations[user_id],
                })
                for uid, conns in _connections.items():
                    if uid == user_id:
                        continue
                    for conn in conns:
                        try:
                            await conn.send_text(payload)
                        except Exception:
                            pass

            elif msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    finally:
        _connections[user_id].remove(ws)
        if not _connections[user_id]:
            del _connections[user_id]
            _locations.pop(user_id, None)
