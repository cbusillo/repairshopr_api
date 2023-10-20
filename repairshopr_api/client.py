import logging
import json
import time

import pytz
import requests

from config import config

logger = logging.getLogger(__name__)


class Client(requests.Session):
    def __init__(self, token: str = "", base_url: str = ""):
        super().__init__()

        def rate_hook(response_hook, *_args, **_kwargs):
            if response_hook.status_code == 200:
                return

            if response_hook.status_code == 429:
                retry_seconds = 1
                logger.info("rate limit reached, sleeping for %i", retry_seconds)
                time.sleep(retry_seconds)

            if response_hook.status_code == 401:
                logger.error("received authorization error: %s", response_hook.text)

            logger.error("received bad status code: %s", response_hook.text)

        self.token = token or config.repairshopr.token
        self.base_url = base_url or config.repairshopr.base_url
        self.headers.update({"accept": "application/json", "Authorization": self.token})
        self.hooks["response"].append(rate_hook)

    def fetch_products(self) -> dict:
        response = self.get(f"{self.base_url}/products")
        return response.json()


if __name__ == "__main__":
    client = Client()
    products = client.fetch_products()
    print(products)
