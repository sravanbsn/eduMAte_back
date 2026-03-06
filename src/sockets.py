import socketio

# Create a SocketIO server instance with ASGI integration capability
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

# Simple memory store for mapping connected users to SIDs for MVP
user_sockets = {}


@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")


@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")
    # Cleanup memory structure
    for user_id, socket_id in list(user_sockets.items()):
        if socket_id == sid:
            del user_sockets[user_id]
            print(f"User {user_id} removed from tracking.")
            break


@sio.event
async def register(sid, data):
    """
    Registers the connection so we know which student/tutor mapped to this Socket ID
    """
    user_id = data.get("user_id")
    if user_id:
        user_sockets[user_id] = sid
        print(f"User {user_id} registered with SID {sid}")
        await sio.emit("registered", {"status": "success"}, room=sid)


@sio.event
async def join_room(sid, data):
    """
    Allows a student and tutor to join a shared room for signaling.
    """
    room_id = data.get("room_id")
    if room_id:
        await sio.enter_room(sid, room_id)
        print(f"SID {sid} joined room {room_id}")
        await sio.emit("room_joined", {"room_id": room_id}, room=sid)


@sio.event
async def signal_message(sid, data):
    """
    Relays a WebRTC signal (Offer, Answer, ICE Candidate) to a room.
    """
    room_id = data.get("room_id")
    signal_data = data.get("signal")
    if room_id and signal_data:
        # Broadcast the signal to the room, excluding the sender
        await sio.emit(
            "signal_message",
            {"signal": signal_data, "from": sid},
            room=room_id,
            skip_sid=sid,
        )


@sio.event
async def end_session(sid, data):
    """
    Ends the signaling session and notifies the room.
    """
    room_id = data.get("room_id")
    if room_id:
        await sio.emit(
            "session_ended",
            {"message": "The session has ended."},
            room=room_id,
            skip_sid=sid,
        )
        await sio.leave_room(sid, room_id)
        print(f"SID {sid} left room {room_id} and ended session.")
