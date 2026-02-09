from __future__ import annotations

from datetime import datetime, timedelta, timezone

from repairshopr_api.models.user import User


class StubClient:
    def __init__(self, updated_at: datetime | None) -> None:
        self.updated_at = updated_at
        self.fetch_calls: list[int] = []

    def fetch_from_api_by_id(self, _model: type[User], instance_id: int) -> dict:
        self.fetch_calls.append(instance_id)
        return {
            "email": "refreshed@example.com",
            "full_name": "Refreshed User",
        }


def test_user_post_init_skips_refresh_when_recent_sync() -> None:
    client = StubClient(updated_at=datetime.now() - timedelta(hours=6))
    User.rs_client = client

    user = User(id=12)

    assert user.email is None
    assert client.fetch_calls == []


def test_user_post_init_fetches_when_sync_is_old() -> None:
    client = StubClient(updated_at=datetime.now(tz=timezone.utc) - timedelta(days=3))
    User.rs_client = client

    user = User(id=42)

    assert client.fetch_calls == [42]
    assert user.email == "refreshed@example.com"
    assert user.full_name == "Refreshed User"


def test_user_post_init_aware_vs_naive_regression() -> None:
    client = StubClient(updated_at=datetime.now(tz=timezone.utc) - timedelta(days=2))
    User.rs_client = client

    user = User(id=99)

    assert user.email == "refreshed@example.com"

