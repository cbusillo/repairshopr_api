import logging
from datetime import datetime
from http import HTTPStatus
from typing import Any, Generator, Protocol, TypeVar

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from repairshopr_api.base.model import BaseModel
from repairshopr_api.config import config
from repairshopr_api import models

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

ModelType = TypeVar("ModelType", bound="ModelProtocol")


class ModelProtocol(Protocol):
    @classmethod
    def from_dict(cls: type[ModelType], data: dict) -> ModelType:
        ...


class Client(requests.Session):
    MAX_RETRIES = 5
    _cache = {}

    def __init__(self, token: str = "", url_store_name: str = ""):
        super().__init__()
        if not url_store_name:
            url_store_name = config.repairshopr.url_store_name
        if not token:
            token = config.repairshopr.token
        if not url_store_name or not token:
            raise ValueError("url_store_name and token must be provided in either the constructor or the config file.")

        self.token = token or config.repairshopr.token
        self.base_url = f"https://{url_store_name}.repairshopr.com/api/v1"
        self.headers.update({"accept": "application/json", "Authorization": self.token})
        BaseModel.set_client(self)

    def clear_cache(self) -> None:
        self._cache.clear()

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

        elif response.status_code == HTTPStatus.NOT_FOUND.value:
            logger.warning("Received 404 error: %s", response.text)
            raise ValueError("Received 404 error.")

        elif response.status_code != HTTPStatus.OK.value:
            logger.warning("Request failed with status code %s. Retrying...", response.status_code)
            raise requests.RequestException(
                f"Received unexpected status code: {response.status_code}. Response content: {response.text}"
            )

        return response

    def fetch_from_api(self, model_name: str, params: dict[str, str] = None) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        response = self.get(f"{self.base_url}/{model_name}s", params=params)
        return response.json()[f"{model_name}s"], response.json().get("meta")

    def fetch_from_api_by_id(self, model: type[ModelType], instance_id: int) -> ModelType:
        cache_key = f"{model.__name__.lower()}_{instance_id}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        response = self.get(f"{self.base_url}/{model.__name__.lower()}s/{instance_id}")
        response_data = response.json()[model.__name__.lower()]
        result = None
        if isinstance(response_data, dict):
            result = model.from_dict(response_data)
        elif isinstance(response_data, list):
            result = model.from_list(response_data)

        if not result:
            logger.warning(f"Could not find {model.__name__} with id {instance_id}")
            raise ValueError(f"Could not find {model.__name__} with id {instance_id}")
        self._cache[cache_key] = result
        return result

    def get_model_data(
        self, model: type[ModelType], updated_at: datetime = None, params: dict = None
    ) -> Generator[ModelType, None, None]:
        if not params:
            params = {}

        if updated_at:
            params["since_updated_at"] = updated_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        page = 1
        while True:
            params["page"] = page

            response_data, meta_data = self.fetch_from_api(model.__name__.lower(), params=params)
            for data in response_data:
                if isinstance(data, dict):
                    yield model.from_dict(data)
                elif isinstance(data, list):
                    yield model.from_list(data)

            if page >= meta_data.get("total_pages", 0):
                break

            page += 1


if __name__ == "__main__":
    client = Client()

    print(client.fetch_from_api_by_id(models., 5205024))
    test_objects = client.get_model_data(models.Customer, updated_at=datetime(2023, 10, 11))
    count = 0
    for test_object in test_objects:
        print(test_object.business_and_full_name)
        for contact in test_object.contacts:
            print(f"--{contact.name}  {contact.updated_at}")

        count += 1
