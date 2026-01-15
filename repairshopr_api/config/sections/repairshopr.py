from repairshopr_api.config.serializable import Serializable


class Repairshopr(Serializable):
    token: str = ""
    url_store_name: str = ""
