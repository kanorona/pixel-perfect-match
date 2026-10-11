"""Small Phoenix-compatible room protocol for the Supabase Realtime client."""

from dataclasses import dataclass
from secrets import token_hex

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect

from app.auth import ApiError, PUBLIC_KEY, require_api_key, store_from
from app.models import BroadcastRequest

router = APIRouter(tags=["Realtime"])


@dataclass
class Client:
    socket: WebSocket
    topic: str
    join_ref: str | None
    key: str | None = None
    peer: dict | None = None
    phx_ref: str | None = None


class RoomHub:
    def __init__(self) -> None:
        self.rooms: dict[str, list[Client]] = {}

    async def join(self, client: Client) -> None:
        self.rooms.setdefault(client.topic, []).append(client)
        state = {
            member.key: {"metas": [{**member.peer, "phx_ref": member.phx_ref}]}
            for member in self.rooms[client.topic]
            if member.key and member.peer
        }
        await self.send(client, "presence_state", state)

    async def leave(self, client: Client) -> None:
        members = self.rooms.get(client.topic, [])
        if client in members:
            members.remove(client)
        if client.key and client.peer:
            await self._presence_diff(client, joins={}, leaves={
                client.key: {"metas": [{**client.peer, "phx_ref": client.phx_ref}]}
            })
        if not members:
            self.rooms.pop(client.topic, None)

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
        for member in list(self.rooms.get(client.topic, [])):
            await self.send(member, "presence_diff", {"joins": joins, "leaves": leaves})

    async def broadcast(self, topic: str, event: str, payload: dict, sender: Client | None = None) -> None:
        for member in list(self.rooms.get(topic, [])):
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
            message = await socket.receive_json()
            if not isinstance(message, list) or len(message) != 5:
                await socket.close(code=1003)
                return
            join_ref, ref, topic, event, payload = message
            if event == "heartbeat" and topic == "phoenix":
                await socket.send_json(reply(join_ref, ref, topic))
                continue
            if event == "phx_join":
                session_id = str(topic).removeprefix("room:")
                if not str(topic).startswith("room:") or session_id not in socket.app.state.store.sessions:
                    await socket.send_json(reply(join_ref, ref, topic, "error", {"reason": "unknown room"}))
                    continue
                if client:
                    await hub.leave(client)
                client = Client(socket=socket, topic=topic, join_ref=join_ref)
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
