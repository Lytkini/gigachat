from http import HTTPStatus
from typing import Any, Dict, Optional

import httpx

from gigachat.api.utils import build_headers
from gigachat.exceptions import AuthenticationError, ResponseError
from gigachat.models.threads import ThreadRunOptions, ThreadRunResponse


def _get_kwargs(
    *,
    thread_id: str,
    thread_options: Optional[ThreadRunOptions] = None,
    access_token: Optional[str] = None,
) -> Dict[str, Any]:
    headers = build_headers(access_token)
    thread_options_dict = {}
    if thread_options:
        thread_options_dict = thread_options.dict(exclude_none=True)
    params = {
        "method": "POST",
        "url": "/threads/run",
        "headers": headers,
        "json": {**thread_options_dict, **{"thread_id": thread_id}},
    }
    return params


def _build_response(response: httpx.Response) -> ThreadRunResponse:
    if response.status_code == HTTPStatus.OK:
        return ThreadRunResponse(**response.json())
    elif response.status_code == HTTPStatus.UNAUTHORIZED:
        raise AuthenticationError(response.url, response.status_code, response.content, response.headers)
    else:
        raise ResponseError(response.url, response.status_code, response.content, response.headers)


def sync(
    client: httpx.Client,
    *,
    thread_id: str,
    thread_options: Optional[ThreadRunOptions] = None,
    access_token: Optional[str] = None,
) -> ThreadRunResponse:
    """Получить результат run треда"""
    kwargs = _get_kwargs(thread_id=thread_id, thread_options=thread_options, access_token=access_token)
    response = client.request(**kwargs)
    return _build_response(response)


async def asyncio(
    client: httpx.AsyncClient,
    *,
    thread_id: str,
    thread_options: Optional[ThreadRunOptions] = None,
    access_token: Optional[str] = None,
) -> ThreadRunResponse:
    """Получить результат run треда"""
    kwargs = _get_kwargs(thread_id=thread_id, thread_options=thread_options, access_token=access_token)
    response = await client.request(**kwargs)
    return _build_response(response)
