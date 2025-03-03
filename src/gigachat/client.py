import logging
from functools import cached_property
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    Iterator,
    Optional,
    TypeVar,
    Union,
)

import httpx

from gigachat.api import get_model, get_models, post_auth, post_chat, post_token, stream_chat
from gigachat.exceptions import AuthenticationError
from gigachat.models import (
    AccessToken,
    Chat,
    ChatCompletion,
    ChatCompletionChunk,
    Model,
    Models,
    Token,
)
from gigachat.settings import Settings

T = TypeVar("T")

logger = logging.getLogger(__name__)


def _get_kwargs(settings: Settings) -> Dict[str, Any]:
    """Настройки для подключения к API GIGACHAT"""
    return {
        "base_url": settings.base_url,
        "verify": settings.verify_ssl_certs,
        "timeout": httpx.Timeout(settings.timeout),
    }


def _get_auth_kwargs(settings: Settings) -> Dict[str, Any]:
    """Настройки для подключения к серверу авторизации OAuth 2.0"""
    return {
        "verify": settings.verify_ssl_certs,
        "timeout": httpx.Timeout(settings.timeout),
    }


def _parse_chat(chat: Union[Chat, Dict[str, Any]], model: Optional[str]) -> Chat:
    payload = Chat.parse_obj(chat)
    if model:
        payload.model = model
    return payload


def _build_access_token(token: Token) -> AccessToken:
    return AccessToken(access_token=token.tok, expires_at=token.exp)


class _BaseClient:
    _access_token: Optional[AccessToken] = None

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        auth_url: Optional[str] = None,
        credentials: Optional[str] = None,
        scope: Optional[str] = None,
        access_token: Optional[str] = None,
        model: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        timeout: Optional[float] = None,
        verify_ssl_certs: Optional[bool] = None,
        use_auth: Optional[bool] = None,
        verbose: Optional[bool] = None,
    ) -> None:
        config = {k: v for k, v in locals().items() if k != "self" and v is not None}
        self._settings = Settings(**config)
        if self._settings.access_token:
            self._access_token = AccessToken(access_token=self._settings.access_token, expires_at=0)

    @property
    def token(self) -> Optional[str]:
        if self._settings.use_auth and self._access_token:
            return self._access_token.access_token
        else:
            return None

    @property
    def _use_auth(self) -> bool:
        return self._settings.use_auth

    def _check_validity_token(self) -> bool:
        """Проверить время завершения действия токена"""
        if self._access_token:
            # _check_validity_token
            return True
        return False

    def _reset_token(self) -> None:
        """Сбросить токен"""
        self._access_token = None


class GigaChatSyncClient(_BaseClient):
    """Синхронный клиент GigaChat"""

    @cached_property
    def _client(self) -> httpx.Client:
        return httpx.Client(**_get_kwargs(self._settings))

    @cached_property
    def _auth_client(self) -> httpx.Client:
        return httpx.Client(**_get_auth_kwargs(self._settings))

    def close(self) -> None:
        self._client.close()
        self._auth_client.close()

    def __enter__(self) -> "GigaChatSyncClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def _update_token(self) -> None:
        if self._settings.credentials:
            self._access_token = post_auth.sync(
                self._auth_client,
                url=self._settings.auth_url,
                credentials=self._settings.credentials,
                scope=self._settings.scope,
            )
            logger.info("OAUTH UPDATE TOKEN")
        elif self._settings.user and self._settings.password:
            self._access_token = _build_access_token(
                post_token.sync(self._client, user=self._settings.user, password=self._settings.password)
            )
            logger.info("UPDATE TOKEN")

    def _decorator(self, call: Callable[..., T]) -> T:
        if self._use_auth:
            if self._check_validity_token():
                try:
                    return call()
                except AuthenticationError:
                    logger.warning("AUTHENTICATION ERROR")
                    self._reset_token()
            self._update_token()
        return call()

    def get_models(self) -> Models:
        """Возвращает массив объектов с данными доступных моделей"""
        return self._decorator(lambda: get_models.sync(self._client, access_token=self.token))

    def get_model(self, model: str) -> Model:
        """Возвращает объект с описанием указанной модели"""
        return self._decorator(lambda: get_model.sync(self._client, model=model, access_token=self.token))

    def chat(self, payload: Union[Chat, Dict[str, Any]]) -> ChatCompletion:
        """Возвращает ответ модели с учетом переданных сообщений"""
        chat = _parse_chat(payload, model=self._settings.model)
        return self._decorator(lambda: post_chat.sync(self._client, chat=chat, access_token=self.token))

    def stream(self, payload: Union[Chat, Dict[str, Any]]) -> Iterator[ChatCompletionChunk]:
        """Возвращает ответ модели с учетом переданных сообщений"""
        chat = _parse_chat(payload, model=self._settings.model)

        if self._use_auth:
            if self._check_validity_token():
                try:
                    for chunk in stream_chat.sync(self._client, chat=chat, access_token=self.token):
                        yield chunk
                    return
                except AuthenticationError:
                    logger.warning("AUTHENTICATION ERROR")
                    self._reset_token()
            self._update_token()

        for chunk in stream_chat.sync(self._client, chat=chat, access_token=self.token):
            yield chunk


class GigaChatAsyncClient(_BaseClient):
    """Асинхронный клиент GigaChat"""

    @cached_property
    def _aclient(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(**_get_kwargs(self._settings))

    @cached_property
    def _auth_aclient(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(**_get_auth_kwargs(self._settings))

    async def aclose(self) -> None:
        await self._aclient.aclose()
        await self._auth_aclient.aclose()

    async def __aenter__(self) -> "GigaChatAsyncClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def _aupdate_token(self) -> None:
        if self._settings.credentials:
            self._access_token = await post_auth.asyncio(
                self._auth_aclient,
                url=self._settings.auth_url,
                credentials=self._settings.credentials,
                scope=self._settings.scope,
            )
            logger.info("OAUTH UPDATE TOKEN")
        elif self._settings.user and self._settings.password:
            self._access_token = _build_access_token(
                await post_token.asyncio(self._aclient, user=self._settings.user, password=self._settings.password)
            )
            logger.info("UPDATE TOKEN")

    async def _adecorator(self, acall: Callable[..., Awaitable[T]]) -> T:
        if self._use_auth:
            if self._check_validity_token():
                try:
                    return await acall()
                except AuthenticationError:
                    logger.warning("AUTHENTICATION ERROR")
                    self._reset_token()
            await self._aupdate_token()
        return await acall()

    async def aget_models(self) -> Models:
        """Возвращает массив объектов с данными доступных моделей"""

        async def _acall() -> Models:
            return await get_models.asyncio(self._aclient, access_token=self.token)

        return await self._adecorator(_acall)

    async def aget_model(self, model: str) -> Model:
        """Возвращает объект с описанием указанной модели"""

        async def _acall() -> Model:
            return await get_model.asyncio(self._aclient, model=model, access_token=self.token)

        return await self._adecorator(_acall)

    async def achat(self, payload: Union[Chat, Dict[str, Any]]) -> ChatCompletion:
        """Возвращает ответ модели с учетом переданных сообщений"""
        chat = _parse_chat(payload, model=self._settings.model)

        async def _acall() -> ChatCompletion:
            return await post_chat.asyncio(self._aclient, chat=chat, access_token=self.token)

        return await self._adecorator(_acall)

    async def astream(self, payload: Union[Chat, Dict[str, Any]]) -> AsyncIterator[ChatCompletionChunk]:
        """Возвращает ответ модели с учетом переданных сообщений"""
        chat = _parse_chat(payload, model=self._settings.model)

        if self._use_auth:
            if self._check_validity_token():
                try:
                    async for chunk in stream_chat.asyncio(self._aclient, chat=chat, access_token=self.token):
                        yield chunk
                    return
                except AuthenticationError:
                    logger.warning("AUTHENTICATION ERROR")
                    self._reset_token()
            await self._aupdate_token()

        async for chunk in stream_chat.asyncio(self._aclient, chat=chat, access_token=self.token):
            yield chunk
