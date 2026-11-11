"""Small Phoenix-compatible room protocol for the Supabase Realtime client."""

import json
from dataclasses import dataclass
from secrets import token_hex

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect

from app.auth import ApiError, PUBLIC_KEY, require_api_key, store_from
from app.metrics import ApplicationMetrics
from app.models import BroadcastRequest

router = APIRouter(tags=["Realtime"])


@dataclass
class Client:
    socket: WebSocket
    topic: str
    room: str
    join_ref: str | None
    key: str | None = None
    peer: dict | None = None
    phx_ref: str | None = None


def room_key(topic: str) -> str | None:
    """Normalize SDK topics and HTTP fallback topics to one room key."""
    room = topic.removeprefix("realtime:")
    if not room.startswith("room:") or not room[5:]:
        return None
    return room


def decode_binary_broadcast(data: bytes) -> list:
    """Decode the SDK's version-2 user broadcast push (kind 3, JSON payload)."""
    if len(data) < 7 or data[0] != 3 or data[6] != 1:
        raise ValueError("Unsupported binary Realtime frame")
    lengths = data[1:6]
    if len(data) < 7 + sum(lengths):
        raise ValueError("Incomplete binary Realtime frame")
    offset = 7
    fields = []
    for length in lengths:
        fields.append(data[offset:offset + length].decode("utf-8"))
        offset += length
    join_ref, ref, topic, event, _metadata = fields
    payload = json.loads(data[offset:].decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object in Realtime broadcast")
    return [join_ref or None, ref or None, topic, "broadcast", {"event": event, "payload": payload}]


async def receive_message(socket: WebSocket) -> list:
    frame = await socket.receive()
    if frame["type"] == "websocket.disconnect":
        raise WebSocketDisconnect(frame.get("code", 1000))
    if frame.get("bytes") is not None:
        return decode_binary_broadcast(frame["bytes"])
    message = json.loads(frame.get("text") or "null")
    if not isinstance(message, list) or len(message) != 5:
        raise ValueError("Expected a five-element Realtime message")
    return message


class RoomHub:
    def __init__(self, metrics: ApplicationMetrics) -> None:
        self.rooms: dict[str, list[Client]] = {}
        self.metrics = metrics

    async def join(self, client: Client) -> None:
        self.rooms.setdefault(client.room, []).append(client)
        self.metrics.active_participants.add(1)
        state = {
            member.key: {"metas": [{**member.peer, "phx_ref": member.phx_ref}]}
            for member in self.rooms[client.room]
            if member.key and member.peer
        }
        await self.send(client, "presence_state", state)

    async def leave(self, client: Client) -> None:
        members = self.rooms.get(client.room, [])
        if client in members:
            members.remove(client)
            self.metrics.active_participants.add(-1)
        if client.key and client.peer:
            await self._presence_diff(client, joins={}, leaves={
                client.key: {"metas": [{**client.peer, "phx_ref": client.phx_ref}]}
            })
        if not members:
            self.rooms.pop(client.room, None)

    async def track(self, client: Client, peer: dict) -> None:
        client.key = str(peer.get("id", ""))
        client.peer = peer
        client.phx_ref = token_hex(8)
        await self._presence_diff(client, joins={
            client.key: {"metas": [{**peer, "phx_ref": client.phx_ref}]}
        }, leaves={})

    async def untrack(self, client: Client) -> None:
        if client.key and client.peer:
            await self._presence_diff(client, joins={}, leaves={
                client.key: {"metas": [{**client.peer, "phx_ref": client.phx_ref}]}
            })
        client.key = client.peer = client.phx_ref = None

    async def _presence_diff(self, client: Client, joins: dict, leaves: dict) -> None:
        for member in list(self.rooms.get(client.room, [])):
            await self.send(member, "presence_diff", {"joins": joins, "leaves": leaves})

    async def broadcast(self, topic: str, event: str, payload: dict, sender: Client | None = None) -> None:
        for member in list(self.rooms.get(room_key(topic), [])):
            if member is not sender:
                await self.send(member, "broadcast", {"event": event, "payload": payload})

    @staticmethod
    async def send(client: Client, event: str, payload: dict) -> None:
        await client.socket.send_json([client.join_ref, None, client.topic, event, payload])


def reply(join_ref: str | None, ref: str | None, topic: str, status: str = "ok", response: dict | None = None) -> list:
    return [join_ref, ref, topic, "phx_reply", {"status": status, "response": response or {}}]


@router.websocket("/realtime/v1/websocket")
async def websocket_room(socket: WebSocket) -> None:
    await socket.accept()
    if socket.query_params.get("apikey") != PUBLIC_KEY:
        await socket.close(code=1008)
        return
    hub: RoomHub = socket.app.state.hub
    client: Client | None = None
    try:
        while True:
            try:
                join_ref, ref, topic, event, payload = await receive_message(socket)
            except (ValueError, UnicodeDecodeError):
                await socket.close(code=1003)
                return
            if not isinstance(payload, dict):
                await socket.close(code=1003)
                return
            if event == "heartbeat" and topic == "phoenix":
                await socket.send_json(reply(join_ref, ref, topic))
                continue
            if event == "phx_join":
                room = room_key(str(topic))
                if not room or not socket.app.state.store.session_exists(room[5:]):
                    await socket.send_json(reply(join_ref, ref, topic, "error", {"reason": "unknown room"}))
                    continue
                if client:
                    await hub.leave(client)
                client = Client(socket=socket, topic=topic, room=room, join_ref=join_ref)
                await socket.send_json(reply(join_ref, ref, topic))
                await hub.join(client)
                continue
            if not client or client.topic != topic:
                await socket.send_json(reply(join_ref, ref, topic, "error", {"reason": "not joined"}))
                continue
            if event == "phx_leave":
                await socket.send_json(reply(join_ref, ref, topic))
                await hub.leave(client)
                client = None
            elif event == "presence":
                if payload.get("event") == "track":
                    await hub.track(client, payload.get("payload") or {})
                elif payload.get("event") == "untrack":
                    await hub.untrack(client)
                await socket.send_json(reply(join_ref, ref, topic))
            elif event == "broadcast":
                await hub.broadcast(topic, payload.get("event", ""), payload.get("payload") or {}, client)
                await socket.send_json(reply(join_ref, ref, topic))
            else:
                await socket.send_json(reply(join_ref, ref, topic))
    except WebSocketDisconnect:
        pass
    finally:
        if client:
            await hub.leave(client)


@router.post("/realtime/v1/api/broadcast", dependencies=[Depends(require_api_key)])
async def broadcast_fallback(body: BroadcastRequest, request: Request) -> dict:
    hub: RoomHub = request.app.state.hub
    for message in body.messages:
        if message.private:
            raise ApiError(400, "Private rooms are not supported", "invalid_room")
        await hub.broadcast(message.topic, message.event, message.payload)
    return {"status": "ok"}
