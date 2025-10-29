import logging
from logging.config import dictConfig
from typing import Any, Annotated

import uvicorn
from fastapi import Depends, FastAPI, Request
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
    def __init__(self, request: Request) -> None:
        # Из-за то что request это тип из старлейт, не нужно Depends, чтобы фастапи прокинул его по сервисам до сюда.
        # Он и так это сделает
        self.request = request

    async def get_request(self) -> dict[str, Any]:
        print(f'------------------------- {id(self)}')
        debugging_header = self.request.headers.get("debugging")
        if debugging_header:
            # То что ты и просил. Не могу понять только, почему ты хотел чтобы это работало как сингилтон
            logger.info("Debugging header received: %s", debugging_header)

        return {"rows": ["mocked", "data"]}


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


app = FastAPI()


@app.get("/health")
async def read_health(
    service: Annotated[DataService, Depends(DataService)] = None,  # тут обязательно депенс
) -> dict[str, Any]:
    data = await service.get_payload()
    return data


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_config=LOG_CONFIG, log_level="info")
