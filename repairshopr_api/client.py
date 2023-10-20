import logging
from datetime import datetime
from http import HTTPStatus
from typing import Any, Generator, Protocol, TypeVar

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from repairshopr_api.config import config
from repairshopr_api import models

logger = logging.getLogger(__name__)

ModelType = TypeVar("T", bound="ModelProtocol")


class ModelProtocol(Protocol):
    @classmethod
    def from_dict(cls: type[ModelType], data: dict) -> ModelType:
        ...


class Client(requests.Session):
    MAX_RETRIES = 5
    PAGE_SIZE = 25

    def __init__(self, token: str = "", base_url: str = ""):
        super().__init__()

        self.token = token or config.repairshopr.token
        self.base_url = (base_url or config.repairshopr.base_url).rstrip("/")
        self.headers.update({"accept": "application/json", "Authorization": self.token})

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(min=1, max=10),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def request(self, method: str, url: str, *args, **kwargs) -> requests.Response:
        response = super().request(method, url, *args, **kwargs)

        if response.status_code == HTTPStatus.TOO_MANY_REQUESTS.value:
            logger.info("Rate limit reached. Waiting and retrying...")
            raise requests.RequestException("Rate limit reached")

        elif response.status_code == HTTPStatus.UNAUTHORIZED.value:
            logger.error("Received authorization error: %s", response.text)
            raise PermissionError("Authorization failed with the provided token.")

        elif response.status_code != HTTPStatus.OK.value:
            logger.warning("Request failed with status code %s. Retrying...", response.status_code)
            raise requests.RequestException(
                f"Received unexpected status code: {response.status_code}. Response content: {response.text}"
            )

        return response

    def fetch_from_api(self, model_name: str, params: dict = None) -> tuple[list[dict], dict]:
        response = self.get(f"{self.base_url}/{model_name}s", params=params)
        return response.json()[f"{model_name}s"], response.json()["meta"]

    def get_model_data(self, model: type[ModelProtocol], updated_at: datetime = None) -> Generator[ModelType, None, None]:
        page = 1
        while True:
            params = {"page": page}
            if updated_at:
                params["updated_at"] = updated_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

            response_data, meta_data = self.fetch_from_api(model.__name__.lower(), params=params)
            for data in response_data:
                yield model.from_dict(data)

            if page >= meta_data["total_pages"]:
                break

            page += 1


if __name__ == "__main__":
    client = Client()
    test_products = client.get_model_data(models.Product)
    print(test_products)
