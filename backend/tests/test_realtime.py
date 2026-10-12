import json

import pytest

from app.auth import PUBLIC_KEY


def receive_event(socket, event, topic=None):
    for _ in range(12):
        message = socket.receive_json()
        if message[3] == event and (topic is None or message[2] == topic):
            return message
    raise AssertionError(f"No {event} event received")


def sdk_binary_broadcast(topic, event, payload):
    # realtime-js v2 sends broadcast pushes as kind-3 binary frames.
    fields = [b"1", b"5", topic.encode("utf-8"), event.encode("utf-8"), b""]
    header = bytes([3, *(len(field) for field in fields), 1])
    return header + b"".join(fields) + json.dumps(payload, ensure_ascii=False).encode("utf-8")


@pytest.mark.parametrize("prefix", ["", "realtime:"])
def test_two_clients_share_broadcast_and_presence(client, signed_in, prefix):
    _, headers = signed_in
    session_id = client.get("/rest/v1/interview_sessions", headers=headers).json()[0]["id"]
    topic = f"{prefix}room:{session_id}"
    path = f"/realtime/v1/websocket?apikey={PUBLIC_KEY}&vsn=2.0.0"
    with client.websocket_connect(path) as first, client.websocket_connect(path) as second:
        first.send_json(["1", "1", topic, "phx_join", {"config": {}}])
        assert receive_event(first, "phx_reply")[4]["status"] == "ok"
        receive_event(first, "presence_state")
        second.send_json(["2", "2", topic, "phx_join", {"config": {}}])
        assert receive_event(second, "phx_reply")[4]["status"] == "ok"
        receive_event(second, "presence_state")

        first.send_json(["1", "3", topic, "presence", {"type": "presence", "event": "track",
                                                  "payload": {"id": "interviewer", "name": "Demo",
                                                              "role": "interviewer", "color": "blue"}}])
        diff = receive_event(second, "presence_diff")
        assert "interviewer" in diff[4]["joins"]
        first.send_json(["1", "4", topic, "broadcast",
                         {"type": "broadcast", "event": "cursor", "payload": {"id": "interviewer", "x": 1}}])
        assert receive_event(second, "broadcast")[4]["payload"]["x"] == 1
        first.send_bytes(sdk_binary_broadcast(topic, "sync-req", {"name": "Niña"}))
        binary_event = receive_event(second, "broadcast")
        assert binary_event[4]["event"] == "sync-req"
        assert binary_event[4]["payload"]["name"] == "Niña"
        response = client.post("/realtime/v1/api/broadcast", headers=headers, json={"messages": [{
            "topic": f"room:{session_id}", "event": "cursor", "payload": {"x": 2}, "private": False,
        }]})
        assert response.status_code == 200
        assert receive_event(second, "broadcast")[4]["payload"]["x"] == 2
        first.send_json([None, "5", "phoenix", "heartbeat", {}])
        assert receive_event(first, "phx_reply", "phoenix")[2] == "phoenix"
