import logging
import time
from collections import Counter, defaultdict, deque
from contextlib import contextmanager
from datetime import datetime, timedelta
from http import HTTPStatus
from typing import Any, Generator, Protocol, TypeVar

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings
from repairshopr_api import models
from repairshopr_api.base.model import BaseModel
from repairshopr_api.converters.strings import snake_case

logger = logging.getLogger(__name__)
if settings.debug:
    logger.setLevel(logging.INFO)
    logging.basicConfig(level=logging.INFO)

ModelType = TypeVar("ModelType", bound="ModelProtocol")


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
            url_store_name = settings.repairshopr.url_store_name
        if not token:
            token = settings.repairshopr.token
        if not url_store_name or not token:
            raise ValueError("url_store_name and token must be provided in either the constructor or the config file.")

        self.token = token or settings.repairshopr.token
        self.base_url = f"https://{url_store_name}.repairshopr.com/api/v1"
        self.headers.update({"accept": "application/json", "Authorization": self.token})
        self.updated_at: datetime | None = None
        self._has_line_item_in_cache = False
        self.api_call_counter = Counter()
        self.api_call_type = defaultdict(list)
        self.api_call_duration = defaultdict(list)
        self.api_sleep_time = 0.0
        BaseModel.set_client(self)

    def _clear_old_request_timestamps(self) -> None:
        current_time = datetime.now()
        while self._request_timestamps and self._request_timestamps[0] < current_time - timedelta(seconds=60):
            self._request_timestamps.popleft()

    def _wait_for_rate_limit(self) -> None:
        self._clear_old_request_timestamps()
        if len(self._request_timestamps) > self.REQUEST_LIMIT:
            oldest_request = self._request_timestamps[0]
            sleep_time = 60 - (datetime.now() - oldest_request).total_seconds()
            if sleep_time > 0:
                time.sleep(sleep_time)
                self.api_sleep_time += sleep_time

            self._clear_old_request_timestamps()

        self._request_timestamps.append(datetime.now())

    def display_api_call_stats(self) -> None:
        stats_str = "API Stats: "
        total_time = 0.0
        for api_call_type, durations in self.api_call_duration.items():
            if durations:
                average_duration = sum(durations) / len(durations)
                count = self.api_call_counter.get(api_call_type, 0)
                stats_str += f"{api_call_type} (C: {count}, A: {average_duration:.3f}s), "
                total_time += sum(durations)
        api_request_time = timedelta(seconds=total_time)

        logger.info(
            f"{stats_str.rstrip(', ')} * Request t: {api_request_time.total_seconds():.2f} | Sleep t: {self.api_sleep_time:.2f}s | Calls last 60s: {len(self._request_timestamps)}"
        )

    @contextmanager
    def time_api_call(self, url: str, **kwargs) -> None:
        if logger.isEnabledFor(logging.INFO):
            last_part = url.split("/")[-1]
            is_id = last_part.isdigit()
            invoice_id = kwargs.get("params", {}).get("invoice_id")
            estimate_id = kwargs.get("params", {}).get("estimate_id")

            if is_id:
                api_call_type = f"{url.split('/')[-2]}_direct"
            elif invoice_id or estimate_id:
                api_call_type = f"{last_part}_lookup"
            else:
                api_call_type = f"{last_part}_bulk"

            self.api_call_counter[api_call_type] += 1
            start_time = datetime.now()
            yield None
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            self.api_call_duration[api_call_type].append(duration)
            self.display_api_call_stats()
        else:
            yield None

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(min=30, max=180),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def request(self, method: str, url: str, *args, **kwargs) -> requests.Response:
        self._wait_for_rate_limit()
        with self.time_api_call(url, **kwargs):
            response = super().request(method, url, *args, **kwargs)

        match response.status_code:
            case HTTPStatus.OK:
                pass

            case HTTPStatus.TOO_MANY_REQUESTS:
                logger.info("Rate limit reached. Waiting and retrying...")
                raise requests.RequestException("Rate limit reached")

            case HTTPStatus.UNAUTHORIZED:
                logger.error("Received authorization error: %s", response.text)
                raise PermissionError("Authorization failed with the provided token.")

            case HTTPStatus.NOT_FOUND:
                logger.warning("Received 404 error: %s", response.text)
                raise ValueError("Received 404 error.")

            case _:
                logger.warning("Request failed with status code %s. Retrying...", response.status_code)
                raise requests.RequestException(
                    f"Received unexpected status code: {response.status_code}. Response content: {response.text}"
                )

        return response

    def clear_cache(self) -> None:
        self._cache.clear()
        self._has_line_item_in_cache = False

    def prefetch_line_items(self) -> None:
        if self._has_line_item_in_cache:
            return
        if self.updated_at and self.updated_at > datetime.now() - timedelta(weeks=52):
            return
        logger.info("Prefetching line items...")
        lines_items = list(self.get_model(models.LineItem, params={"invoice_id_not_null": "true"}))

        invoice_line_item_map = defaultdict(list)
        for line_item in lines_items:
            invoice_id = line_item.invoice_id
            invoice_line_item_map[invoice_id].append(
                {key: value for key, value in line_item.__dict__.items() if not key.startswith("_")}
            )

        for invoice_id, line_items in invoice_line_item_map.items():
            total_entries = len(line_items)
            total_pages = -(-total_entries // 100)

            for page in range(1, total_pages + 1):
                start_index = (page - 1) * 100
                end_index = start_index + 100
                paginated_line_items = line_items[start_index:end_index]

                meta_data = {"page": page, "per_page": 100, "total_entries": total_entries, "total_pages": total_pages}
                cache_data = (paginated_line_items, meta_data)

                params = {"invoice_id": invoice_id}
                if page > 1:
                    params["page"] = page
                sorted_params = tuple(sorted(params.items()))
                cache_key = f"line_item_list_{hash(sorted_params)}"
                self._cache[cache_key] = cache_data

        self._has_line_item_in_cache = True

    def fetch_from_api(self, model_name: str, params: dict[str, str] = None) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        cache_key = f"{model_name}_list"
        if params:
            sorted_params = tuple(sorted(params.items()))
            cache_key += f"_{hash(sorted_params)}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        response = self.get(f"{self.base_url}/{model_name}s", params=params)
        result = response.json()[f"{model_name}s"], response.json().get("meta")
        self._cache[cache_key] = result

        return result

    def fetch_from_api_by_id(self, model: type[ModelType], instance_id: int) -> dict[str, Any]:
        if model.__name__ == "LineItem" and "invoice" in model.__module__:
            self.prefetch_line_items()
        cache_key = f"{model.__name__.lower()}_{instance_id}"

        if cache_key in self._cache:
            return self._cache[cache_key]
        try:
            response = self.get(f"{self.base_url}/{snake_case(model.__name__)}s/{instance_id}")
            response_data = response.json()[model.__name__.lower()]
            result = response_data

            if not result:
                logger.warning(f"Could not find {model.__name__} with id {instance_id}")
                raise ValueError(f"Could not find {model.__name__} with id {instance_id}")
            self._cache[cache_key] = result
            return result
        except ValueError:
            logger.warning(f"Could not find {model.__name__} with id {instance_id}")

    def get_model(
        self, model: type[ModelType], updated_at: datetime = None, num_last_pages: int = None, params: dict = None
    ) -> Generator[ModelType, None, None]:
        if not params:
            params = {}

        if updated_at:
            self.updated_at = updated_at
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

            if not meta_data or page >= meta_data.get("total_pages", 0):
                break
            if page == 1 and meta_data.get("total_pages", 0) > 1 and num_last_pages:
                page = max(1, meta_data.get("total_pages", 0) - num_last_pages + 1)
            page += 1

    def get_model_by_id(self, model: type[ModelType], instance_id: int) -> ModelType:
        return model.from_dict(self.fetch_from_api_by_id(model, instance_id))


if __name__ == "__main__":
    client = Client()

    #  print(client.fetch_from_api_by_id(models.Estimate, 4796157))
    #  print(client.get_properties_fields(models.Ticket))
    #  print(client.get_model(models.Ticket))
