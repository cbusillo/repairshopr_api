import logging
import time
from http import HTTPStatus

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from config import config

logger = logging.getLogger(__name__)


class Client(requests.Session):
    MAX_RETRIES = 5

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
            logger.warning(f"Request failed with status code {response.status_code}. Retrying...")
            raise requests.RequestException(
                f"Received unexpected status code: {response.status_code}. Response content: {response.text}"
            )

        return response

    def fetch_products(self) -> dict:
        response = self.get(f"{self.base_url}/products")
        return response.json()


if __name__ == "__main__":
    client = Client()
    products = client.fetch_products()
    print(products)
