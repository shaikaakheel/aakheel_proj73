
from aiohttp import web
import asyncio
import uuid

users = {}
calls = {}
accepted_calls = set()

HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>My Video Calling App</title>

<style>
body {
    background: #101827;
    color: white;
    font-family: Arial;
    padding: 15px;
}
.container {
    max-width: 600px;
    margin: auto;
    background: #1e293b;
    padding: 20px;
    border-radius: 15px;
}
button {
    padding: 12px 16px;
    margin: 5px;
    border: 0;
    border-radius: 8px;
    font-weight: bold;
}
.call, .accept { background: #22c55e; }
.reject, .end { background: #ef4444; color: white; }
.user {
    background: #334155;
    padding: 12px;
    margin: 10px 0;
    border-radius: 8px;
}
video {
    width: 100%;
    background: black;
    border-radius: 12px;
    margin-top: 10px;
}
#incoming, #active { display: none; }
#status { color: #4ade80; }
</style>
</head>

<body>
<div class="container">

<h1>My Video Calling App</h1>

<p id="status">Connecting...</p>
<p id="myid"></p>

<h2>Online Users</h2>
<div id="users"></div>

<div id="incoming">
    <h2>Incoming Call</h2>
    <p id="caller"></p>
    <button class="accept" onclick="acceptCall()">Accept</button>
    <button class="reject" onclick="rejectCall()">Reject</button>
</div>

<div id="active">
    <h2>Video Call</h2>

    <p id="callStatus">Connecting...</p>

    <h3>Remote Video</h3>
    <video id="remoteVideo" autoplay playsinline></video>

    <h3>Your Video</h3>
    <video id="localVideo" autoplay muted playsinline></video>

    <button class="end" onclick="endCall()">End Call</button>
</div>

</div>

<script>
const protocol =
    location.protocol === "https:" ? "wss:" : "ws:";

const ws = new WebSocket(
    protocol + "//" + location.host + "/ws"
);

let myId = null;
let incomingCaller = null;
let currentCall = null;
let pc = null;
let localStream = null;
let pendingCandidates = [];

const rtcConfig = {
    iceServers: [
        { urls: "stun:stun.l.google.com:19302" },
        { urls: "stun:stun1.l.google.com:19302" }
    ]
};

function send(data) {
    if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(data));
    }
}

async function getMedia() {
    if (!localStream) {
        localStream = await navigator.mediaDevices.getUserMedia({
            video: true,
            audio: true
        });

        document.getElementById("localVideo").srcObject =
            localStream;
    }

    return localStream;
}

async function createPeer() {
    if (pc) return pc;

    const stream = await getMedia();

    pc = new RTCPeerConnection(rtcConfig);

    stream.getTracks().forEach(track => {
        pc.addTrack(track, stream);
    });

    pc.ontrack = event => {
        document.getElementById("remoteVideo").srcObject =
            event.streams[0];
    };

    pc.onicecandidate = event => {
        if (event.candidate) {
            send({
                type: "candidate",
                candidate: event.candidate.toJSON()
            });
        }
    };

    pc.onconnectionstatechange = () => {
        if (!pc) return;

        const state = pc.connectionState;

        document.getElementById("callStatus").textContent =
            "Connection: " + state;

        if (state === "failed" || state === "closed") {
            document.getElementById("callStatus").textContent =
                "Connection failed or closed";
        }
    };

    return pc;
}

async function addRemoteCandidate(candidate) {
    if (!pc || !pc.remoteDescription) {
        pendingCandidates.push(candidate);
        return;
    }

    try {
        await pc.addIceCandidate(candidate);
    } catch (error) {
        console.error("ICE candidate error:", error);
    }
}

async function flushCandidates() {
    const candidates = pendingCandidates;
    pendingCandidates = [];

    for (const candidate of candidates) {
        await addRemoteCandidate(candidate);
    }
}

async function startOffer() {
    const peer = await createPeer();

    const offer = await peer.createOffer();

    await peer.setLocalDescription(offer);

    send({
        type: "offer",
        description: {
            type: peer.localDescription.type,
            sdp: peer.localDescription.sdp
        }
    });
}

async function handleOffer(description) {
    const peer = await createPeer();

    await peer.setRemoteDescription(description);

    await flushCandidates();

    const answer = await peer.createAnswer();

    await peer.setLocalDescription(answer);

    send({
        type: "answer",
        description: {
            type: peer.localDescription.type,
            sdp: peer.localDescription.sdp
        }
    });
}

async function handleAnswer(description) {
    if (!pc) return;

    await pc.setRemoteDescription(description);

    await flushCandidates();
}

function resetCall() {
    if (pc) {
        pc.close();
        pc = null;
    }

    if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
        localStream = null;
    }

    document.getElementById("localVideo").srcObject = null;
    document.getElementById("remoteVideo").srcObject = null;

    document.getElementById("incoming").style.display = "none";
    document.getElementById("active").style.display = "none";

    incomingCaller = null;
    currentCall = null;
    pendingCandidates = [];
}

async function startCall(target) {
    if (currentCall || incomingCaller) return;

    currentCall = target;

    send({
        type: "call",
        target: target
    });
}

function acceptCall() {
    if (!incomingCaller) return;

    currentCall = incomingCaller;

    send({
        type: "accept",
        target: incomingCaller
    });

    document.getElementById("incoming").style.display = "none";
    document.getElementById("active").style.display = "block";
    document.getElementById("callStatus").textContent =
        "Call accepted. Connecting...";
}

function rejectCall() {
    if (!incomingCaller) return;

    send({
        type: "reject",
        target: incomingCaller
    });

    resetCall();
}

function endCall() {
    if (currentCall) {
        send({
            type: "end",
            target: currentCall
        });
    }

    resetCall();
    document.getElementById("status").textContent =
        "Call ended";
}

ws.onopen = () => {
    document.getElementById("status").textContent =
        "Connected to server";
};

ws.onmessage = async event => {
    const data = JSON.parse(event.data);

    try {
        if (data.type === "welcome") {
            myId = data.id;
            document.getElementById("myid").textContent =
                "Your ID: " + myId;
        }

        else if (data.type === "users") {
            const container = document.getElementById("users");
            container.replaceChildren();

            data.users.forEach(user => {
                if (user.id === myId) return;

                const item = document.createElement("div");
                item.className = "user";

                const label = document.createElement("span");
                label.textContent = "User: " + user.id;

                const button = document.createElement("button");
                button.className = "call";
                button.textContent = "Call";
                button.disabled = !!currentCall || !!incomingCaller;

                button.onclick = () => startCall(user.id);

                item.appendChild(label);
                item.appendChild(button);
                container.appendChild(item);
            });
        }

        else if (data.type === "incoming_call") {
            if (currentCall || incomingCaller) return;

            incomingCaller = data.from;

            document.getElementById("caller").textContent =
                "User " + data.from + " is calling you.";

            document.getElementById("incoming").style.display =
                "block";
        }

        else if (data.type === "call_outgoing") {
            document.getElementById("status").textContent =
                "Calling " + data.target + "...";
        }

        else if (data.type === "call_accepted") {
            currentCall = data.from;

            document.getElementById("active").style.display =
                "block";

            document.getElementById("incoming").style.display =
                "none";

            document.getElementById("callStatus").textContent =
                "Starting video...";

            if (data.from !== myId) {
                await startOffer();
            }
        }

        else if (data.type === "offer") {
            await handleOffer(data.description);
        }

        else if (data.type === "answer") {
            await handleAnswer(data.description);
        }

        else if (data.type === "candidate") {
            await addRemoteCandidate(data.candidate);
        }

        else if (data.type === "call_rejected") {
            alert("Call rejected.");
            resetCall();
        }

        else if (data.type === "call_ended") {
            alert("The other user ended the call.");
            resetCall();
        }

        else if (data.type === "error") {
            alert(data.message);
            if (data.message.includes("busy") ||
                data.message.includes("already")) {
                resetCall();
            }
        }
    } catch (error) {
        console.error(error);
        document.getElementById("callStatus").textContent =
            "Call error: " + error.message;
    }
};

ws.onclose = () => {
    document.getElementById("status").textContent =
        "Disconnected";
    resetCall();
};

ws.onerror = () => {
    document.getElementById("status").textContent =
        "WebSocket connection error";
};

</script>
</body>
</html>
"""


async def home(request):
    return web.Response(text=HTML, content_type="text/html")


async def send_to(user_id, data):
    ws = users.get(user_id)

    if ws and not ws.closed:
        await ws.send_json(data)
        return True

    return False


def find_call(user_id):
    for caller, receiver in calls.items():
        if user_id == caller or user_id == receiver:
            return caller, receiver
    return None


async def broadcast_users():
    message = {
        "type": "users",
        "users": [{"id": uid} for uid in users]
    }

    await asyncio.gather(
        *[
            ws.send_json(message)
            for ws in list(users.values())
            if not ws.closed
        ],
        return_exceptions=True
    )


async def websocket_handler(request):
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)

    user_id = str(uuid.uuid4())[:8]
    users[user_id] = ws

    print("User joined:", user_id)

    await ws.send_json({
        "type": "welcome",
        "id": user_id
    })

    await broadcast_users()

    try:
        async for msg in ws:

            if msg.type != web.WSMsgType.TEXT:
                continue

            try:
                data = msg.json()
            except Exception:
                continue

            action = data.get("type")
            target = data.get("target")

            if action in ("call", "accept", "reject", "end"):

                if not isinstance(target, str) or target not in users:
                    await ws.send_json({
                        "type": "error",
                        "message": "User is offline."
                    })
                    continue

            if action == "call":

                if find_call(user_id) or find_call(target):
                    await ws.send_json({
                        "type": "error",
                        "message": "A user is already in a call or busy."
                    })
                    continue

                calls[user_id] = target

                await send_to(target, {
                    "type": "incoming_call",
                    "from": user_id
                })

                await ws.send_json({
                    "type": "call_outgoing",
                    "target": target
                })

                print(user_id, "calling", target)

            elif action == "accept":

                if calls.get(target) != user_id:
                    continue

                accepted_calls.add(target)

                await send_to(target, {
                    "type": "call_accepted",
                    "from": user_id
                })

                await ws.send_json({
                    "type": "call_accepted",
                    "from": target
                })

                print(user_id, "accepted call")

            elif action == "reject":

                if calls.get(target) != user_id:
                    continue

                calls.pop(target, None)

                await send_to(target, {
                    "type": "call_rejected"
                })

                print(user_id, "rejected call")

            elif action == "end":

                pair = find_call(user_id)

                if not pair:
                    continue

                caller, receiver = pair
                calls.pop(caller, None)
                accepted_calls.discard(caller)

                other = receiver if user_id == caller else caller

                await send_to(other, {
                    "type": "call_ended"
                })

                print(user_id, "ended call")

            elif action in ("offer", "answer", "candidate"):

                pair = find_call(user_id)

                if not pair or pair[0] not in accepted_calls:
                    continue

                caller, receiver = pair
                other = receiver if user_id == caller else caller

                message = {"type": action}

                if action == "candidate":
                    candidate = data.get("candidate")
                    if not isinstance(candidate, dict):
                        continue
                    message["candidate"] = candidate

                else:
                    description = data.get("description")
                    if not isinstance(description, dict):
                        continue
                    if description.get("type") not in ("offer", "answer"):
                        continue
                    if not isinstance(description.get("sdp"), str):
                        continue
                    message["description"] = description

                await send_to(other, message)

    finally:
        users.pop(user_id, None)

        pair = find_call(user_id)

        if pair:
            caller, receiver = pair
            calls.pop(caller, None)
            accepted_calls.discard(caller)

            other = receiver if user_id == caller else caller

            await send_to(other, {
                "type": "call_ended"
            })

        print("User disconnected:", user_id)
        await broadcast_users()

    return ws


app = web.Application()
app.router.add_get("/", home)
app.router.add_get("/ws", websocket_handler)


if __name__ == "__main__":
    print("Starting Video Calling Server...")
    web.run_app(app, host="0.0.0.0", port=5000)
