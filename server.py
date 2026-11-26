
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
    print("Starting Video Calling Server at http://192.168.31.39:7373")
    web.run_app(app, host="0.0.0.0", port=7373)
