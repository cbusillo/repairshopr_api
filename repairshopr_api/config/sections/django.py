from datetime import datetime

from repairshopr_api.config.serializable import Serializable


class Django(Serializable):
    last_updated_at: datetime | None = None
