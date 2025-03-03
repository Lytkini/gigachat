from http import HTTPStatus
from typing import Any, AsyncIterator, Dict, Iterator, Optional

import httpx

from gigachat.exceptions import AuthenticationError, ResponseError
from gigachat.models import Chat, ChatCompletionChunk

EVENT_STREAM = "text/event-stream"


def _get_kwargs(
    *,
    chat: Chat,
    access_token: Optional[str] = None,
    client_id: Optional[str] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    headers = {
        "Accept": EVENT_STREAM,
        "Cache-Control": "no-store",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if client_id:
        headers["X-Client-ID"] = client_id
    if session_id:
        headers["X-Session-ID"] = session_id
    if request_id:
        headers["X-Request-ID"] = request_id

    return {
        "method": "POST",
        "url": "/chat/completions",
        "json": {**chat.dict(exclude_none=True), **{"stream": True}},
        "headers": headers,
    }


def _parse_chunk(line: str) -> Optional[ChatCompletionChunk]:
    name, _, value = line.partition(": ")
    if name == "data":
        if value == "[DONE]":
            return None
        else:
            return ChatCompletionChunk.parse_raw(value)
    else:
        return None


def _check_content_type(response: httpx.Response) -> None:
    content_type, _, _ = response.headers.get("content-type", "").partition(";")
    if content_type != EVENT_STREAM:
        raise httpx.TransportError(f"Expected response Content-Type to be '{EVENT_STREAM}', got {content_type!r}")


def _check_response(response: httpx.Response) -> None:
    if response.status_code == HTTPStatus.OK:
        _check_content_type(response)
    elif response.status_code == HTTPStatus.UNAUTHORIZED:
        raise AuthenticationError(response.url, response.status_code, b"", response.headers)
    else:
        raise ResponseError(response.url, response.status_code, b"", response.headers)


def sync(
    client: httpx.Client,
    *,
    chat: Chat,
    access_token: Optional[str] = None,
    client_id: Optional[str] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Iterator[ChatCompletionChunk]:
    kwargs = _get_kwargs(
        chat=chat, access_token=access_token, client_id=client_id, session_id=session_id, request_id=request_id
    )
    with client.stream(**kwargs) as response:
        _check_response(response)
        for line in response.iter_lines():
            if chunk := _parse_chunk(line):
                yield chunk


async def asyncio(
    client: httpx.AsyncClient,
    *,
    chat: Chat,
    access_token: Optional[str] = None,
    client_id: Optional[str] = None,
    session_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> AsyncIterator[ChatCompletionChunk]:
    kwargs = _get_kwargs(
        chat=chat, access_token=access_token, client_id=client_id, session_id=session_id, request_id=request_id
    )
    async with client.stream(**kwargs) as response:
        _check_response(response)
        async for line in response.aiter_lines():
            if chunk := _parse_chunk(line):
                yield chunk
