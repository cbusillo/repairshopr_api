from datetime import datetime

from config.serializable import Serializable


class Django(Serializable):
    secret_key: str = ""
    last_updated_at: datetime | None = None
