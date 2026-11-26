from aiohttp import web
import asyncio
import uuid

# In-memory presence/call state. Run one server process for this version.
users = {}          # user_id -> WebSocketResponse
calls = {}          # caller_id -> callee_id
accepted_calls = set()  # caller IDs whose calls were accepted
chat_history = {}  # sorted pair of user IDs -> private message list

HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Video Calling</title>
<style>
:root {
    color-scheme: dark;
    --page: #080f1d;
    --surface: #111c2e;
    --surface-2: #17253a;
    --surface-3: #20314a;
    --line: rgba(148, 163, 184, .16);
    --muted: #9aabc2;
    --text: #f4f7fb;
    --brand: #7c9cff;
    --brand-strong: #5b7cfa;
    --green: #35d49a;
    --red: #ff647c;
}
* { box-sizing: border-box; }
body {
    margin: 0; min-height: 100vh; padding: 28px 18px;
    background:
        radial-gradient(ellipse at 15% 0%, rgba(91,124,250,.16), transparent 38%),
        radial-gradient(ellipse at 100% 30%, rgba(53,212,154,.08), transparent 32%),
        var(--page);
    color: var(--text);
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
button { font: inherit; }
.container { width: min(100%, 980px); margin: 0 auto; }
.topbar {
    display: flex; align-items: center; justify-content: space-between;
    gap: 16px; margin-bottom: 28px;
}
.brand { display: flex; align-items: center; gap: 12px; }
.brand-mark {
    width: 42px; height: 42px; display: grid; place-items: center;
    border-radius: 13px; color: white; font-size: 20px; font-weight: 800;
    background: linear-gradient(145deg, #7898ff, #536ce2);
    box-shadow: 0 8px 28px rgba(83,108,226,.28);
}
.brand-name { font-size: 17px; font-weight: 750; letter-spacing: -.3px; }
.brand-sub { color: var(--muted); font-size: 12px; margin-top: 2px; }
.connection-pill {
    display: inline-flex; align-items: center; gap: 8px; padding: 8px 12px;
    border: 1px solid var(--line); border-radius: 999px;
    background: rgba(17,28,46,.8); color: var(--muted); font-size: 12px;
}
.connection-dot { width: 7px; height: 7px; border-radius: 50%; background: #f6b94b; }
.hero {
    display: flex; align-items: flex-end; justify-content: space-between;
    gap: 18px; margin-bottom: 22px;
}
.eyebrow {
    color: #9db3ff; font-size: 11px; font-weight: 800;
    letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 10px;
}
h1 { margin: 0; font-size: clamp(27px, 5vw, 40px); line-height: 1.08; letter-spacing: -1.4px; }
.hero-copy { max-width: 560px; color: var(--muted); line-height: 1.6; margin: 11px 0 0; font-size: 14px; }
.panel {
    background: linear-gradient(160deg, rgba(23,37,58,.96), rgba(15,26,43,.98));
    border: 1px solid var(--line); border-radius: 20px;
    box-shadow: 0 18px 60px rgba(0,0,0,.18);
}
.lobby { padding: 22px; }
.section-head {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; margin-bottom: 15px;
}
.section-head h2 { font-size: 16px; letter-spacing: -.2px; margin: 0; }
.count-pill {
    padding: 5px 9px; border-radius: 999px; background: rgba(53,212,154,.1);
    color: #75e5bb; font-size: 11px; font-weight: 750;
}
#status { color: var(--muted); font-size: 13px; margin: 0 0 8px; overflow-wrap: anywhere; }
#myid { color: #8295b0; font-size: 11px; margin: 0 0 18px; }
#users { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; }
.user {
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; min-width: 0; padding: 13px;
    background: rgba(32,49,74,.65); border: 1px solid var(--line);
    border-radius: 14px; overflow-wrap: anywhere;
}
.user span { font-size: 13px; font-weight: 650; }
.user span::before {
    content: ""; display: inline-block; width: 8px; height: 8px;
    margin-right: 9px; border-radius: 50%; background: var(--green);
    box-shadow: 0 0 0 4px rgba(53,212,154,.1); vertical-align: 1px;
}
button {
    border: 1px solid transparent; border-radius: 10px; padding: 10px 15px;
    font-size: 12px; font-weight: 750; cursor: pointer;
    transition: transform .15s ease, filter .15s ease, background .15s ease;
}
button:hover:not(:disabled) { filter: brightness(1.08); transform: translateY(-1px); }
button:active:not(:disabled) { transform: translateY(0); }
button:disabled { opacity: .4; cursor: not-allowed; }
.call, .accept {
    background: linear-gradient(135deg, #7e9cff, #5d79ed);
    color: white; box-shadow: 0 5px 16px rgba(93,121,237,.2);
}
.reject, .end { background: #e94e6a; color: white; }
.secondary { background: var(--surface-3); color: var(--text); border-color: var(--line); }
#incoming {
    display: none; margin-top: 16px; padding: 18px;
    background: rgba(91,124,250,.09); border: 1px solid rgba(124,156,255,.25);
    border-radius: 15px;
}
#incoming h2 { font-size: 16px; margin: 0 0 6px; }
#caller { color: var(--muted); font-size: 13px; }
#secureWarning {
    display: none; margin: 0 0 18px; padding: 13px 15px;
    border-radius: 12px; background: rgba(234,123,64,.12);
    border: 1px solid rgba(234,123,64,.3); color: #ffd4b5;
    line-height: 1.5; font-size: 12px;
}
.empty-state {
    grid-column: 1 / -1; padding: 28px 16px; text-align: center;
    border: 1px dashed var(--line); border-radius: 14px; color: var(--muted);
    font-size: 13px;
}
.footer-note { color: #71839c; text-align: center; font-size: 11px; margin: 17px 0 0; }
#callScreen {
    display: none; position: fixed; inset: 0; z-index: 20;
    padding: max(14px, env(safe-area-inset-top)) 16px max(16px, env(safe-area-inset-bottom));
    background: #070d18; flex-direction: column; gap: 12px;
}
#callScreen.visible { display: flex; }
.call-top {
    width: min(100%, 1100px); margin: 0 auto; display: flex;
    justify-content: space-between; align-items: center; gap: 12px;
}
.call-title { font-size: 14px; font-weight: 800; }
.call-subtitle { color: var(--muted); font-size: 11px; margin-top: 3px; }
#callStatus { color: #a9bcff; font-size: 12px; text-align: right; margin: 0; }
.video-stage {
    position: relative; width: min(100%, 1100px); min-height: 0;
    flex: 1; margin: 0 auto; overflow: hidden; border-radius: 18px;
    background: #101a2b; border: 1px solid var(--line);
}
#remoteVideo {
    display: block; width: 100%; height: 100%; min-height: 220px;
    object-fit: contain; background: #101a2b;
}
#localVideo {
    position: absolute; right: 18px; top: 18px; z-index: 2;
    width: clamp(108px, 22vw, 190px); aspect-ratio: 3 / 4;
    object-fit: cover; background: #26364e; border: 2px solid rgba(255,255,255,.8);
    border-radius: 14px; box-shadow: 0 10px 28px rgba(0,0,0,.4);
}
.call-controls {
    display: flex; justify-content: center; align-items: center;
    flex-wrap: wrap; gap: 9px; padding: 3px 0 4px;
}
.call-controls button { min-width: 116px; padding: 13px 17px; }
@media (max-width: 600px) {
    body { padding: 18px 13px; }
    .hero { display: block; }
    .lobby { padding: 16px; }
    .topbar { margin-bottom: 23px; }
    #users { grid-template-columns: 1fr; }
    .video-stage { border-radius: 13px; }
    #localVideo { right: 10px; top: 10px; }
    .call-controls { gap: 7px; }
    .call-controls button { min-width: 0; flex: 1 1 28%; padding: 12px 8px; font-size: 11px; }
}

.user-actions { display:flex; align-items:center; gap:7px; flex-shrink:0; }
.message-btn { background:#273958; color:#dce6fb; border:1px solid rgba(148,163,184,.18); }
.user.self { border-color:rgba(124,156,255,.35); background:rgba(91,124,250,.09); }
.user.self span::before { background:#7c9cff; box-shadow:0 0 0 4px rgba(124,156,255,.1); }
#onlineCount { font-variant-numeric:tabular-nums; }
#chatPanel {
    display:none; position:fixed; z-index:30; right:22px; bottom:22px;
    width:min(390px, calc(100vw - 24px)); height:min(570px, calc(100dvh - 44px));
    background:#101c30; border:1px solid rgba(148,163,184,.24); border-radius:19px;
    box-shadow:0 24px 80px rgba(0,0,0,.55); overflow:hidden;
    flex-direction:column;
}
#chatPanel.open { display:flex; }
.chat-head { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:15px 16px; background:#17263d; border-bottom:1px solid var(--line); }
.chat-peer { min-width:0; }
.chat-peer strong { display:block; font-size:14px; }
.chat-peer small { color:var(--muted); font-size:11px; }
.chat-close { background:#273958; color:white; padding:8px 11px; }
#chatMessages { flex:1; overflow-y:auto; padding:15px; display:flex; flex-direction:column; gap:9px; }
.chat-note { text-align:center; color:var(--muted); font-size:11px; padding:5px; }
.chat-bubble { max-width:84%; padding:10px 12px; border-radius:14px; font-size:13px; line-height:1.45; overflow-wrap:anywhere; }
.chat-bubble.mine { align-self:flex-end; color:white; background:#5d79ed; border-bottom-right-radius:5px; }
.chat-bubble.theirs { align-self:flex-start; color:#e8eef8; background:#263852; border-bottom-left-radius:5px; }
.chat-time { display:block; opacity:.7; font-size:10px; margin-top:4px; }
.chat-compose { display:flex; gap:8px; padding:12px; border-top:1px solid var(--line); background:#142238; }
#chatInput { min-width:0; flex:1; padding:11px 12px; border-radius:11px; border:1px solid var(--line); outline:none; background:#0c1729; color:white; font:inherit; font-size:13px; }
#chatInput:focus { border-color:#7c9cff; }
#chatSend { background:#647ff1; color:white; min-width:48px; }
@media(max-width:600px) {
    #chatPanel { right:10px; bottom:10px; width:calc(100vw - 20px); height:min(70dvh, 560px); }
    .user { align-items:flex-start; }
    .user-actions { gap:5px; }
    .user-actions button { padding:9px 10px; }
}

</style>
</head>
<body>
<main class="container">
    <header class="topbar">
        <div class="brand">
            <div class="brand-mark">V</div>
            <div>
                <div class="brand-name">VConnect</div>
                <div class="brand-sub">Private local video calling</div>
            </div>
        </div>
        <div class="connection-pill">
            <span class="connection-dot"></span>
            Same Wi-Fi network
        </div>
    </header>

    <section class="hero">
        <div>
            <div class="eyebrow">Your private calling space</div>
            <h1>People, closer.</h1>
            <p class="hero-copy">Choose someone who is online and start a secure, one-to-one audio and video conversation on your local network.</p>
        </div>
    </section>

    <section class="panel lobby">
        <div class="section-head">
            <h2>People online</h2>
            <span class="count-pill"><span id="onlineCount">0</span> online</span>
        </div>
        <p id="status">Connecting to your calling server…</p>
        <p id="myid"></p>
        <div id="secureWarning">
            Camera and microphone access requires HTTPS on phones and other computers.
            Open this application through a trusted HTTPS address. Plain HTTP on a LAN IP
            is generally blocked by mobile browsers.
        </div>
        <div id="users"><div class="empty-state">Connecting to the user list…</div></div>

        <section id="incoming">
            <h2>Incoming call</h2>
            <p id="caller"></p>
            <button class="accept" onclick="acceptCall()">Accept call</button>
            <button class="reject" onclick="rejectCall()">Decline</button>
        </section>
    </section>
    <p class="footer-note">VConnect · Local network calling · Your call is peer-to-peer</p>
</main>


<section id="chatPanel" aria-label="Private one-to-one chat">
    <header class="chat-head">
        <div class="chat-peer">
            <strong id="chatTitle">Private chat</strong>
            <small>One-to-one conversation</small>
        </div>
        <button class="chat-close" onclick="closeChat()" aria-label="Close chat">✕</button>
    </header>
    <div id="chatMessages"><div class="chat-note">Messages are private between these two users.</div></div>
    <form class="chat-compose" onsubmit="sendChatMessage(event)">
        <input id="chatInput" type="text" maxlength="2000" placeholder="Write a message…" autocomplete="off">
        <button id="chatSend" type="submit">Send</button>
    </form>
</section>

<section id="callScreen" aria-label="Video call">
    <header class="call-top">
        <div>
            <div class="call-title">VConnect call</div>
            <div class="call-subtitle">One-to-one audio &amp; video</div>
        </div>
        <p id="callStatus">Preparing your call…</p>
    </header>
    <div class="video-stage">
        <video id="remoteVideo" autoplay playsinline></video>
        <video id="localVideo" autoplay muted playsinline></video>
    </div>
    <div class="call-controls">
        <button id="micButton" class="secondary" onclick="toggleMic()">Mute microphone</button>
        <button id="cameraButton" class="secondary" onclick="toggleCamera()">Turn camera off</button>
        <button class="end" onclick="endCall()">End call</button>
    </div>
</section>

<script>
"use strict";

const wsProtocol = location.protocol === "https:" ? "wss:" : "ws:";
const ws = new WebSocket(wsProtocol + "//" + location.host + "/ws");

let myId = null;
let incomingCaller = null;
let currentCall = null;
let pc = null;
let localStream = null;
let remoteStream = null;
let pendingCandidates = [];
let makingOffer = false;

// Same-Wi-Fi mode: use direct local network paths; no public STUN/TURN server.
const rtcConfig = {
    iceServers: []
};

const $ = id => document.getElementById(id);

if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    $("secureWarning").style.display = "block";
}

function setCallStatus(message) {
    $("callStatus").textContent = message;
}

function send(data) {
    if (ws.readyState !== WebSocket.OPEN) {
        $("status").textContent = "Server connection lost. Refresh this page to reconnect.";
        return false;
    }
    ws.send(JSON.stringify(data));
    return true;
}

function showCallScreen() {
    $("callScreen").classList.add("visible");
}

function hideCallScreen() {
    $("callScreen").classList.remove("visible");
}

async function getMedia() {
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error("Camera/microphone require HTTPS on phones and other devices.");
    }
    if (!localStream) {
        localStream = await navigator.mediaDevices.getUserMedia({
            audio: { echoCancellation: true, noiseSuppression: true },
            video: { facingMode: "user" }
        });
        $("localVideo").srcObject = localStream;
    }
    return localStream;
}

async function createPeer() {
    if (pc) return pc;

    const stream = await getMedia();
    const peer = new RTCPeerConnection(rtcConfig);
    pc = peer;

    stream.getTracks().forEach(track => peer.addTrack(track, stream));

    peer.ontrack = event => {
        if (!remoteStream) {
            remoteStream = new MediaStream();
            $("remoteVideo").srcObject = remoteStream;
        }
        for (const track of event.streams[0].getTracks()) {
            if (!remoteStream.getTracks().some(existing => existing.id === track.id)) {
                remoteStream.addTrack(track);
            }
        }
        $("remoteVideo").play().catch(() => {});
    };

    peer.onicecandidate = event => {
        if (event.candidate && currentCall) {
            send({ type: "candidate", candidate: event.candidate.toJSON() });
        }
    };

    peer.onconnectionstatechange = () => {
        if (pc !== peer) return;
        const state = peer.connectionState;
        setCallStatus("Call connection: " + state);
        if (state === "failed") {
            setCallStatus("Connection failed. A TURN server may be needed for different networks.");
        }
    };

    peer.oniceconnectionstatechange = () => {
        if (pc !== peer) return;
        if (peer.iceConnectionState === "disconnected") {
            setCallStatus("Connection interrupted; trying to reconnect…");
        }
    };

    return peer;
}

async function addRemoteCandidate(candidate) {
    if (!pc || !pc.remoteDescription) {
        pendingCandidates.push(candidate);
        return;
    }
    try {
        await pc.addIceCandidate(candidate);
    } catch (error) {
        console.error("Could not add ICE candidate:", error);
    }
}

async function flushCandidates() {
    const queued = pendingCandidates;
    pendingCandidates = [];
    for (const candidate of queued) {
        await addRemoteCandidate(candidate);
    }
}

async function startOffer() {
    if (makingOffer) return;
    makingOffer = true;
    try {
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
        setCallStatus("Calling… waiting for video connection");
    } finally {
        makingOffer = false;
    }
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
        pc.ontrack = null;
        pc.onicecandidate = null;
        pc.close();
        pc = null;
    }
    if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
        localStream = null;
    }
    remoteStream = null;
    $("localVideo").srcObject = null;
    $("remoteVideo").srcObject = null;
    $("incoming").style.display = "none";
    hideCallScreen();
    incomingCaller = null;
    currentCall = null;
    pendingCandidates = [];
    makingOffer = false;
    $("micButton").textContent = "Mute mic";
    $("cameraButton").textContent = "Turn camera off";
    renderUsers(lastUsers);
}

let lastUsers = [];
let activeChatUser = null;

function renderUsers(users) {
    lastUsers = users || [];
    const container = $("users");
    const fragment = document.createDocumentFragment();
    $("onlineCount").textContent = String(lastUsers.length);

    if (!lastUsers.length) {
        const empty = document.createElement("div");
        empty.className = "empty-state";
        empty.textContent = "No users are online yet. Open VConnect on another device connected to this Wi-Fi.";
        fragment.appendChild(empty);
    } else {
        for (const user of lastUsers) {
            const isSelf = user.id === myId;
            const item = document.createElement("div");
            item.className = "user" + (isSelf ? " self" : "");
            const label = document.createElement("span");
            label.textContent = isSelf ? "You · " + user.id : "User " + user.id;

            const actions = document.createElement("div");
            actions.className = "user-actions";

            if (!isSelf) {
                const messageButton = document.createElement("button");
                messageButton.className = "message-btn";
                messageButton.textContent = "Message";
                messageButton.onclick = () => openChat(user.id);
                actions.appendChild(messageButton);

                const callButton = document.createElement("button");
                callButton.className = "call";
                callButton.textContent = "Call";
                callButton.disabled = !!currentCall || !!incomingCaller;
                callButton.onclick = () => startCall(user.id);
                actions.appendChild(callButton);
            } else {
                const you = document.createElement("small");
                you.textContent = "This device";
                you.style.color = "var(--muted)";
                actions.appendChild(you);
            }

            item.append(label, actions);
            fragment.appendChild(item);
        }
    }

    container.replaceChildren(fragment);
}

function renderChatMessages(messages) {
    const area = $("chatMessages");
    area.replaceChildren();
    if (!messages || !messages.length) {
        const note = document.createElement("div");
        note.className = "chat-note";
        note.textContent = "This is the beginning of your private conversation.";
        area.appendChild(note);
        return;
    }
    for (const message of messages) appendChatMessage(message);
    area.scrollTop = area.scrollHeight;
}

function appendChatMessage(message) {
    const area = $("chatMessages");
    const bubble = document.createElement("div");
    bubble.className = "chat-bubble " + (message.from === myId ? "mine" : "theirs");
    const body = document.createElement("span");
    body.textContent = message.text;
    const time = document.createElement("small");
    time.className = "chat-time";
    time.textContent = message.time || "";
    bubble.append(body, time);
    area.appendChild(bubble);
    area.scrollTop = area.scrollHeight;
}

function openChat(userId) {
    const user = lastUsers.find(item => item.id === userId);
    if (!user || userId === myId) return;
    activeChatUser = userId;
    $("chatTitle").textContent = "User " + userId;
    $("chatPanel").classList.add("open");
    $("chatInput").focus();
    renderChatMessages([]);
    send({ type: "chat_open", target: userId });
}

function closeChat() {
    $("chatPanel").classList.remove("open");
    activeChatUser = null;
}

function sendChatMessage(event) {
    event.preventDefault();
    const input = $("chatInput");
    const message = input.value.trim();
    if (!message || !activeChatUser) return;
    if (send({ type: "chat_send", target: activeChatUser, text: message })) {
        input.value = "";
        input.focus();
    }
}

async function startCall(target) {
    if (currentCall || incomingCaller) return;
    currentCall = target;
    if (!send({ type: "call", target })) {
        currentCall = null;
        return;
    }
    $("status").textContent = "Calling user " + target + "…";
}

function acceptCall() {
    if (!incomingCaller) return;
    currentCall = incomingCaller;
    if (!send({ type: "accept", target: incomingCaller })) {
        currentCall = null;
        return;
    }
    $("incoming").style.display = "none";
    showCallScreen();
    setCallStatus("Accepted. Starting camera and microphone…");
}

function rejectCall() {
    if (!incomingCaller) return;
    send({ type: "reject", target: incomingCaller });
    resetCall();
}

function endCall() {
    if (currentCall) send({ type: "end", target: currentCall });
    resetCall();
    $("status").textContent = "Call ended.";
}

function toggleMic() {
    if (!localStream) return;
    const tracks = localStream.getAudioTracks();
    if (!tracks.length) return;
    const enabled = !tracks[0].enabled;
    tracks.forEach(track => track.enabled = enabled);
    $("micButton").textContent = enabled ? "Mute mic" : "Unmute mic";
}

function toggleCamera() {
    if (!localStream) return;
    const tracks = localStream.getVideoTracks();
    if (!tracks.length) return;
    const enabled = !tracks[0].enabled;
    tracks.forEach(track => track.enabled = enabled);
    $("cameraButton").textContent = enabled ? "Turn camera off" : "Turn camera on";
}

ws.onopen = () => {
    $("status").textContent = "Connected to calling server.";
};

ws.onmessage = async event => {
    let data;
    try {
        data = JSON.parse(event.data);
    } catch (error) {
        return;
    }

    try {
        if (data.type === "welcome") {
            myId = data.id;
            $("myid").textContent = "Your user ID: " + myId;
            renderUsers(lastUsers);
        } else if (data.type === "users") {
            renderUsers(data.users);
        } else if (data.type === "chat_history") {
            if (activeChatUser === data.with) renderChatMessages(data.messages);
        } else if (data.type === "chat_message") {
            if (activeChatUser === data.from || activeChatUser === data.to) {
                appendChatMessage(data.message);
            }
        } else if (data.type === "incoming_call") {
            if (currentCall || incomingCaller) {
                send({ type: "reject", target: data.from });
                return;
            }
            incomingCaller = data.from;
            $("caller").textContent = "User " + data.from + " is calling you.";
            $("incoming").style.display = "block";
        } else if (data.type === "call_outgoing") {
            $("status").textContent = "Ringing user " + data.target + "…";
        } else if (data.type === "call_accepted") {
            currentCall = data.from;
            $("incoming").style.display = "none";
            showCallScreen();
            setCallStatus("Call accepted. Connecting audio and video…");
            if (data.role === "caller") {
                await startOffer();
            }
        } else if (data.type === "offer") {
            await handleOffer(data.description);
        } else if (data.type === "answer") {
            await handleAnswer(data.description);
        } else if (data.type === "candidate") {
            await addRemoteCandidate(data.candidate);
        } else if (data.type === "call_rejected") {
            alert("The other user declined the call.");
            resetCall();
        } else if (data.type === "call_ended") {
            alert("The other user ended the call.");
            resetCall();
        } else if (data.type === "error") {
            alert(data.message);
            resetCall();
        }
    } catch (error) {
        console.error(error);
        setCallStatus("Call error: " + error.message);
    }
};

ws.onclose = () => {
    $("status").textContent = "Disconnected from server. Refresh to reconnect.";
    resetCall();
};
ws.onerror = () => {
    $("status").textContent = "WebSocket connection error.";
};
</script>
</body>
</html>
"""


async def home(request):
    # The page is static: let browsers reuse it briefly and negotiate gzip
    # to reduce the amount of data transferred over Wi-Fi.
    response = web.Response(
        text=HTML,
        content_type="text/html",
        headers={"Cache-Control": "private, max-age=30"}
    )
    response.enable_compression()
    return response


async def send_to(user_id, data):
    ws = users.get(user_id)
    if ws and not ws.closed:
        try:
            await ws.send_json(data)
            return True
        except (ConnectionError, RuntimeError):
            return False
    return False


def find_call(user_id):
    for caller, receiver in calls.items():
        if user_id == caller or user_id == receiver:
            return caller, receiver
    return None


async def broadcast_users():
    message = {"type": "users", "users": [{"id": uid} for uid in list(users)]}
    sockets = [ws.send_json(message) for ws in list(users.values()) if not ws.closed]
    if sockets:
        await asyncio.gather(*sockets, return_exceptions=True)


def clear_call(caller):
    calls.pop(caller, None)
    accepted_calls.discard(caller)


async def websocket_handler(request):
    ws = web.WebSocketResponse(heartbeat=30, compress=False)
    await ws.prepare(request)

    user_id = str(uuid.uuid4())[:8]
    users[user_id] = ws
    print("User joined:", user_id)

    await ws.send_json({"type": "welcome", "id": user_id})
    await broadcast_users()

    try:
        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT:
                continue
            try:
                data = msg.json()
            except (ValueError, TypeError):
                continue
            if not isinstance(data, dict):
                continue

            action = data.get("type")
            target = data.get("target")

            if action == "chat_open":
                if not isinstance(target, str) or target not in users or target == user_id:
                    await ws.send_json({"type": "error", "message": "That user is not online."})
                    continue
                pair_key = tuple(sorted((user_id, target)))
                await ws.send_json({
                    "type": "chat_history",
                    "with": target,
                    "messages": chat_history.get(pair_key, [])[-200:]
                })

            elif action == "chat_send":
                text = data.get("text")
                if not isinstance(target, str) or target not in users or target == user_id:
                    await ws.send_json({"type": "error", "message": "That user is not online."})
                    continue
                if not isinstance(text, str):
                    continue
                text = text.strip()
                if not text or len(text) > 2000:
                    continue

                from datetime import datetime
                message = {
                    "from": user_id,
                    "text": text,
                    "time": datetime.now().strftime("%H:%M")
                }
                pair_key = tuple(sorted((user_id, target)))
                chat_history.setdefault(pair_key, []).append(message)
                chat_history[pair_key] = chat_history[pair_key][-200:]

                # Deliver only to the two participants in this private conversation.
                await ws.send_json({
                    "type": "chat_message", "from": user_id, "to": target,
                    "message": message
                })
                await send_to(target, {
                    "type": "chat_message", "from": user_id, "to": target,
                    "message": message
                })

            elif action == "call":
                if not isinstance(target, str) or target not in users or target == user_id:
                    await ws.send_json({"type": "error", "message": "That user is not available."})
                    continue
                if find_call(user_id) or find_call(target):
                    await ws.send_json({"type": "error", "message": "One of the users is already in a call or ringing."})
                    continue

                calls[user_id] = target
                delivered = await send_to(target, {"type": "incoming_call", "from": user_id})
                if not delivered:
                    clear_call(user_id)
                    await ws.send_json({"type": "error", "message": "The user disconnected. Try again."})
                    continue
                await ws.send_json({"type": "call_outgoing", "target": target})
                print(user_id, "calling", target)

            elif action == "accept":
                if not isinstance(target, str) or calls.get(target) != user_id:
                    await ws.send_json({"type": "error", "message": "This call is no longer available."})
                    continue
                accepted_calls.add(target)
                await send_to(target, {
                    "type": "call_accepted", "from": user_id, "role": "caller"
                })
                await ws.send_json({
                    "type": "call_accepted", "from": target, "role": "receiver"
                })
                print(user_id, "accepted call from", target)

            elif action == "reject":
                if not isinstance(target, str) or calls.get(target) != user_id:
                    continue
                clear_call(target)
                await send_to(target, {"type": "call_rejected"})
                print(user_id, "rejected call from", target)

            elif action == "end":
                pair = find_call(user_id)
                if not pair:
                    continue
                caller, receiver = pair
                other = receiver if user_id == caller else caller
                clear_call(caller)
                await send_to(other, {"type": "call_ended"})
                print(user_id, "ended call")

            elif action in ("offer", "answer", "candidate"):
                pair = find_call(user_id)
                if not pair or pair[0] not in accepted_calls:
                    continue
                caller, receiver = pair
                other = receiver if user_id == caller else caller

                if action == "candidate":
                    candidate = data.get("candidate")
                    if not isinstance(candidate, dict):
                        continue
                    payload = {"type": "candidate", "candidate": candidate}
                else:
                    description = data.get("description")
                    expected_type = "offer" if action == "offer" else "answer"
                    if not isinstance(description, dict):
                        continue
                    if description.get("type") != expected_type or not isinstance(description.get("sdp"), str):
                        continue
                    payload = {"type": action, "description": description}

                await send_to(other, payload)

    finally:
        # Remove only this socket's user entry.
        if users.get(user_id) is ws:
            users.pop(user_id, None)

        pair = find_call(user_id)
        if pair:
            caller, receiver = pair
            other = receiver if user_id == caller else caller
            clear_call(caller)
            await send_to(other, {"type": "call_ended"})

        print("User disconnected:", user_id)
        await broadcast_users()

    return ws


app = web.Application()
app.router.add_get("/", home)
app.router.add_get("/ws", websocket_handler)


if __name__ == "__main__":
    print("Starting Video Calling Server on 0.0.0.0:7373")
    print("LAN URL: http://192.168.31.39:7373")
    print("For camera/microphone on phones and other devices, serve this site over HTTPS.")
    web.run_app(app, host="0.0.0.0", port=7373, access_log=None)
