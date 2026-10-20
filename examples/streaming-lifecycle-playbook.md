# Python GenAI streaming

Use SSE for server-to-client model output. Use WebSockets when the application
needs messages in both directions over the same connection.

The following are book excerpts, with chapter dependencies retained. They are
not standalone applications. Code has not been translated or rewritten.

## Return an async model stream through SSE

Pass the model's async generator to `StreamingResponse` and set
`media_type="text/event-stream"`. The generator must produce SSE-formatted
events. This excerpt uses `app` and `azure_chat_client` defined elsewhere in
the chapter.

```python
# main.py

from typing import Annotated
from fastapi import Body, FastAPI
from fastapi.responses import StreamingResponse
from stream import azure_chat_client

@app.post("/generate/text/stream")
async def serve_text_to_text_stream_controller(
    prompt: Annotated[str, Body()]
) -> StreamingResponse:
    return StreamingResponse(
        azure_chat_client.chat_stream(prompt), media_type="text/event-stream"
    )
```

## Route generated tokens to each request

Separate model generation from network delivery. Assign each request its own
event queue, route tokens to the matching request, and use an explicit end
marker. Here `None` ends the queue consumer; it is not sent as a token.
This method belongs to the chapter's `LLMEngine`.

```python
async def event_generator(self, loop, prompt: str):
   # Create an event queue for this client's request
   queue = asyncio.Queue()
   # Register the prompt with an event queue request to workload manager
   seq_id = self.workload_manager.add_streaming_request(prompt, queue, loop)
   while True:
      # Get next token from queue
      data = await queue.get()
      if data is None:  # End of stream
         break
      yield f"data: {data}\n\n" 
```

This listing uses an unbounded queue and shows no disconnect cleanup. It does
not establish bounded backpressure or upstream cancellation.

## Stream agent events separately from text tokens

LangGraph's `updates` mode streams agent state updates. Treat the event kind
and its data separately; these updates are not raw model tokens. This chapter
excerpt requires an async execution context and a running LangGraph server.

```python
from langgraph_sdk import get_client
client = get_client(url="http://localhost:2024")
# Stream a response from the agent
async for chunk in client.runs.stream(
    None,  # Threadless run
    "agent",  # Name of assistant defined in langgraph.json
    input={
        "messages": [{
            "role": "human",
            "content": "What is LangGraph?",
        }],
    },
    stream_mode="updates",
):
    print(f"Receiving event: {chunk.event}...")
    print(chunk.data)
```

## Handle WebSocket client exits

Catch `WebSocketDisconnect` around the receive loop so an ordinary client exit
does not propagate as an unhandled error. This excerpt uses the chapter's
`app`, `WebSocket`, and `logger` definitions. It demonstrates disconnect
handling, not model-task cancellation.

```python
from fastapi.websockets import WebSocketDisconnect
@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_text(
        "Welcome to the chat room!"
    )
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Message received: {data}")
    except WebSocketDisconnect:
        logger.warning(
            "Connection closed by the client"
        )
```

## Keep streaming responsive

- Keep slow network delivery out of the model-generation loop. Use thread-safe
  queues or locks when handing tokens from a generation thread to a network thread.
- Flush small token batches promptly. Larger batches reduce packet overhead but
  delay visible output; do not wait for the complete answer.
- Let users interrupt generation so inference resources can serve other requests.
- Profile latency with streaming enabled and disabled. Check token emission for
  pauses caused by lock contention or I/O waits.

The excerpts above do not provide a complete implementation of bounded queues,
upstream stream closure, or generation cancellation on client disconnect.
