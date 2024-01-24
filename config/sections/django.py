from datetime import datetime

from config.serializable import Serializable


class Django(Serializable):
    secret_key: str = ""
    last_updated_at: datetime | None = None
    db_engine: str = "mysql"
    db_host: str = "localhost"
    db_name: str = "repairshopr"
    db_user: str = "repairshopr_api"
    db_password: str = ""
