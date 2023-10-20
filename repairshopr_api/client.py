import logging
import json
import time

import pytz
import requests

from config import config


class Client(requests.Session):
    def __init__(self, token: str = "", base_url: str = ""):
        super().__init__()
        self.token = token or config.repairshopr.token
        self.base_url = base_url or config.repairshopr.base_url

        self.headers.update({
            "accept": "application/json",
            "Authorization": self.token
        })

    def fetch_products(self):
        response = response = self.get(f"{self.base_url}/products")
        return response.json()

if __name__ == "__main__":
    client = Client()
    products = client.fetch_products()
    print(products)
