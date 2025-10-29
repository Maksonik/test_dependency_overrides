from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import Any

from fastapi import Depends, FastAPI, Header, Request

logger = logging.getLogger(__name__)


class MockDatabaseService:
    """Base service that simulates a database call."""

    def __init__(self, request: Request | None = None) -> None:
        self._request: Request | None = request

    def with_request(self, request: Request) -> "MockDatabaseService":
        self._request = request
        return self

    @property
    def request(self) -> Request:
        if self._request is None:
            raise RuntimeError("Request is not bound to the service")
        return self._request

    async def fetch_from_db(self) -> dict[str, Any]:
        debugging_header = self.request.headers.get("debugging")
        if debugging_header:
            logger.info("Debugging header received: %s", debugging_header)
        return {"rows": ["mocked", "data"]}


class BusinessService(MockDatabaseService):
    async def enrich_data(self) -> dict[str, Any]:
        payload = await self.fetch_from_db()
        payload["enriched"] = True
        return payload


class DataService(BusinessService):
    async def get_payload(self) -> dict[str, Any]:
        data = await self.enrich_data()
        data["service"] = self.__class__.__name__
        return data


def base_data_service_dependency() -> DataService:
    """Default factory returning a new service instance."""

    return DataService()


def bind_request(
    request: Request,
    service: DataService = Depends(base_data_service_dependency),
) -> DataService:
    """Attach the current request to the shared service instance."""

    return service.with_request(request)


class AppFactory:
    """Factory responsible for building the FastAPI application."""

    def __init__(self) -> None:
        self._app = FastAPI(lifespan=self._lifespan)
        self._configure_routes()

    @property
    def app(self) -> FastAPI:
        return self._app

    async def _lifespan(self, app: FastAPI):
        async with AsyncExitStack() as astack:
            singleton_service = DataService()

            async def get_singleton_service() -> DataService:
                return singleton_service

            app.dependency_overrides.setdefault(
                base_data_service_dependency, get_singleton_service
            )
            yield

    def _configure_routes(self) -> None:
        @self._app.get("/health")
        async def read_health(
            debugging: str | None = Header(default=None),
            service: DataService = Depends(bind_request),
        ) -> dict[str, Any]:
            data = await service.get_payload()
            return {"debugging": debugging, "data": data}


def create_app() -> FastAPI:
    return AppFactory().app


app = create_app()
