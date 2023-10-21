import logging
import re
from collections import deque
from datetime import datetime, time, timedelta
import time
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


def snake_case(input_string: str) -> str:
    return re.sub(r"(?<!^)([A-Z])", r"_\1", input_string).lower()


class ModelProtocol(Protocol):
    @classmethod
    def from_dict(cls: type[ModelType], data: dict) -> ModelType:
        ...


class Client(requests.Session):
    MAX_RETRIES = 50
    REQUEST_LIMIT = 150
    _cache = {}
    _request_timestamps = deque()

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

    def _clear_old_request_timestamps(self) -> None:
        current_time = datetime.now()
        while self._request_timestamps and self._request_timestamps[0] < current_time - timedelta(seconds=60):
            self._request_timestamps.popleft()

    def _wait_for_rate_limit(self) -> None:
        self._clear_old_request_timestamps()
        if len(self._request_timestamps) > self.REQUEST_LIMIT:
            oldest_request = self._request_timestamps[0]
            time.sleep((datetime.now() - oldest_request).total_seconds() + 60)

            self._clear_old_request_timestamps()

        self._request_timestamps.append(datetime.now())

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(min=30, max=180),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def request(self, method: str, url: str, *args, **kwargs) -> requests.Response:
        self._wait_for_rate_limit()
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
        try:
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
        except ValueError:
            logger.warning(f"Could not find {model.__name__} with id {instance_id}")

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
            model_name = snake_case(model.__name__)
            response_data, meta_data = self.fetch_from_api(model_name, params=params)
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

    #  print(client.fetch_from_api_by_id(models.Estimate, 4796157))
    test_objects = client.get_model_data(models.LineItem, updated_at=datetime(2023, 10, 19))
    count = 0
    for test_object in test_objects:
        if not test_object.product or not test_object.invoice:
            continue
        print(f"{test_object.product.description}  {test_object.invoice.customer_business_then_name}")
        #  print(test_object.invoices)
        # for contact in test_object.contacts:
        #     print(f"--{contact.name}  {contact.updated_at}")

        count += 1
