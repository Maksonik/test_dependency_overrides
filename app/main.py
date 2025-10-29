"""Custom FastAPI application with service dependency overrides."""
from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import Depends, FastAPI, Header, Request


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class BaseDataService:
    """Base service responsible for performing a mock database request."""

    def __init__(self) -> None:
        self.request: Optional[Request] = None
        self.debugging_header: Optional[str] = None

    def bind_context(self, request: Request, debugging_header: Optional[str]) -> "BaseDataService":
        self.request = request
        self.debugging_header = debugging_header
        return self

    async def mock_db_request(self) -> dict[str, str]:
        """Simulate database access with optional debug logging."""
        if self.debugging_header:
            client = self.request.client if self.request else None
            logger.info(
                "Debugging '%s' for %s", self.debugging_header, getattr(client, "host", "unknown")
            )
        return {"status": "ok"}


class AuditDataService(BaseDataService):
    """Intermediate service adding transformation capabilities."""

    def inherit_context(self, parent: BaseDataService) -> "AuditDataService":
        self.request = parent.request
        self.debugging_header = parent.debugging_header
        return self

    async def gather_metrics(self) -> dict[str, str]:
        payload = await self.mock_db_request()
        payload.update({"audit": "complete"})
        return payload


class AnalyticsService(AuditDataService):
    """Final service used by the API endpoint."""

    def inherit_context(self, parent: AuditDataService) -> "AnalyticsService":  # type: ignore[override]
        super().inherit_context(parent)
        return self

    async def build_response(self) -> dict[str, str]:
        payload = await self.gather_metrics()
        payload.update({"service": "analytics"})
        return payload


async def provide_base_service_singleton() -> BaseDataService:
    return BaseDataService()


def provide_audit_service_singleton(
    base_service: BaseDataService = Depends(provide_base_service_singleton),
) -> AuditDataService:
    _ = base_service
    return AuditDataService()


def provide_analytics_service_singleton(
    audit_service: AuditDataService = Depends(provide_audit_service_singleton),
) -> AnalyticsService:
    _ = audit_service
    return AnalyticsService()


async def get_base_service(
    request: Request,
    debugging: Optional[str] = Header(default=None, alias="X-Debugging"),
    base_service: BaseDataService = Depends(provide_base_service_singleton),
) -> BaseDataService:
    return base_service.bind_context(request, debugging)


async def get_audit_service(
    audit_service: AuditDataService = Depends(provide_audit_service_singleton),
    base_service: BaseDataService = Depends(get_base_service),
) -> AuditDataService:
    return audit_service.inherit_context(base_service)


async def get_analytics_service(
    analytics_service: AnalyticsService = Depends(provide_analytics_service_singleton),
    audit_service: AuditDataService = Depends(get_audit_service),
) -> AnalyticsService:
    return analytics_service.inherit_context(audit_service)


class CustomFastAPI(FastAPI):
    """FastAPI application with a custom lifespan and singleton services."""

    def __init__(self) -> None:
        super().__init__(lifespan=self.lifespan_context)

    @asynccontextmanager
    async def lifespan_context(self, app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as astack:
            base_service = BaseDataService()
            audit_service = AuditDataService()
            analytics_service = AnalyticsService()

            app.dependency_overrides.setdefault(
                provide_base_service_singleton, lambda: base_service
            )
            app.dependency_overrides.setdefault(
                provide_audit_service_singleton, lambda: audit_service
            )
            app.dependency_overrides.setdefault(
                provide_analytics_service_singleton, lambda: analytics_service
            )

            astack.callback(logger.info, "Services shutdown complete")

            yield

            app.dependency_overrides.pop(provide_base_service_singleton, None)
            app.dependency_overrides.pop(provide_audit_service_singleton, None)
            app.dependency_overrides.pop(provide_analytics_service_singleton, None)


app = CustomFastAPI()


@app.get("/ping")
async def ping(service: AnalyticsService = Depends(get_analytics_service)) -> dict[str, str]:
    return await service.build_response()
