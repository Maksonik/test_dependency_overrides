from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from logging.config import dictConfig
from typing import Any, Annotated, Callable

import uvicorn
from fastapi import Depends, FastAPI
from uvicorn.config import LOGGING_CONFIG as UVICORN_LOGGING


LOG_CONFIG = UVICORN_LOGGING.copy()
LOG_CONFIG["disable_existing_loggers"] = False
LOG_CONFIG["loggers"][__name__] = {
    "handlers": ["default"],
    "level": "INFO",
    "propagate": False,
}
dictConfig(LOG_CONFIG)
logger = logging.getLogger(__name__)



class MockDatabaseService:
    def __init__(self, params: dict[str, str]) -> None:
        self.params = params

    async def get_request(self) -> dict[str, Any]:
        return {"result": self.params}


# Следующие классы чтобы создать видимость наследование
class BusinessService(MockDatabaseService):
    async def get_data(self) -> dict[str, Any]:
        payload = await self.get_request()
        payload["enriched"] = True
        return payload


class DataService(BusinessService):
    async def get_payload(self) -> dict[str, Any]:
        payload = await self.get_data()
        payload["service"] = self.__class__.__name__
        return payload


# Функция для DI, чтобы переписать инициализацию класса на уровне приложение, а не каждого запроса
def di_data_service(params: Any) -> DataService:
    return DataService(params=params)



class AppFactory(FastAPI):
    # это чтобы IDE не ругался что не знает откуда это. Можно по сути удалить
    dependency_overrides: dict[Callable[..., Any], Callable[..., Any]]

    def __init__(self) -> None:
        super().__init__(lifespan=AppFactory.lifespan)

    @staticmethod
    @asynccontextmanager
    async def lifespan(app: AppFactory):
        async with AsyncExitStack() as astack:
            singleton_service = DataService(params={"name": "Alex from lifespan"})
            logger.info("create DataService one times")

            async def get_singleton_service() -> DataService:
                logger.info(f"return singleton_service, id - {id(singleton_service)}")
                return singleton_service

            # вся магия перезаписи! Теперь у нас один обьект на все запрос
            app.dependency_overrides.setdefault(di_data_service, get_singleton_service)
            yield


# можно проще написать lifespan с лямдой (ПС: можно ещё короче, еслис оздавать в лямбе сервис,
# но я разделил эти действия, чтобы было понятно)

#     async def lifespan(app: AppFactory):
#         async with AsyncExitStack() as astack:
#         singleton_service = DataService(params={"name": "Alex from lifespan"})
#         logger.info("create DataService one times")
#         app.dependency_overrides.setdefault(di_data_service, lambda: singleton_service)
#         yield


app = AppFactory()


@app.get("/health")
async def read_health(
    service: Annotated[DataService, Depends(di_data_service)]) -> dict[str, Any]:
    data = await service.get_payload()
    return data


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_config=LOG_CONFIG, log_level="info")
