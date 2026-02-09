from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from django.db import models

from repairshopr_api.config import settings
from repairshopr_data.management.commands import import_from_repairshopr as command_module
from repairshopr_data.management.commands.import_from_repairshopr import (
    _coerce_datetime,
    _parse_datetime,
    create_or_update_django_instance,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.cleared = False

    def get_model(self, model, updated_at, num_last_pages, params):
        self.calls.append((model, updated_at, num_last_pages, params))
        return []

    def clear_cache(self) -> None:
        self.cleared = True

    def fetch_ticket_settings(self) -> dict:
        return {}


@pytest.fixture
def command(monkeypatch: pytest.MonkeyPatch):
    fake_client = FakeClient()
    monkeypatch.setattr(command_module, "Client", lambda: fake_client)
    cmd = command_module.Command()
    return cmd, fake_client


def test_parse_datetime_and_coerce_datetime(caplog: pytest.LogCaptureFixture) -> None:
    parsed = _parse_datetime("2026-01-01T00:00:00Z", field_name="x")
    assert parsed == datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    caplog.set_level(logging.WARNING)
    invalid = _parse_datetime("nope", field_name="x")
    assert invalid is None
    assert "Unable to parse datetime" in caplog.text

    assert _coerce_datetime(date(2026, 1, 2), field_name="x") == datetime(2026, 1, 2, 0, 0, 0)
    assert _coerce_datetime("2026-01-03T00:00:00+00:00", field_name="x") == datetime(
        2026, 1, 3, 0, 0, 0, tzinfo=timezone.utc
    )
    assert _coerce_datetime(1_704_067_200, field_name="x") == datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert _coerce_datetime(object(), field_name="x") is None


def test_handle_model_coerces_naive_last_updated_at(command, monkeypatch: pytest.MonkeyPatch) -> None:
    cmd, fake_client = command
    settings.django.last_updated_at = datetime(2026, 1, 1, 0, 0, 0)

    monkeypatch.setattr(
        cmd,
        "dynamic_import",
        lambda path: type("DjangoModel", (), {}) if path.startswith("repairshopr_data") else type("ApiModel", (), {}),
    )

    cmd.handle_model("repairshopr_data.models.user.User", "repairshopr_api.models.User", num_last_pages=3)

    _, updated_at_arg, num_last_pages_arg, _ = fake_client.calls[0]
    assert updated_at_arg is not None
    assert updated_at_arg.tzinfo is not None
    assert num_last_pages_arg == 3


def test_handle_model_uses_baseline_when_last_updated_is_too_old(command, monkeypatch: pytest.MonkeyPatch) -> None:
    cmd, fake_client = command
    settings.django.last_updated_at = datetime(2000, 1, 1, tzinfo=timezone.utc)

    monkeypatch.setattr(
        cmd,
        "dynamic_import",
        lambda path: type("DjangoModel", (), {}) if path.startswith("repairshopr_data") else type("ApiModel", (), {}),
    )

    cmd.handle_model("repairshopr_data.models.user.User", "repairshopr_api.models.User", num_last_pages=8)

    _, _, num_last_pages_arg, _ = fake_client.calls[0]
    assert num_last_pages_arg is None


def test_handle_model_naive_vs_aware_regression(command, monkeypatch: pytest.MonkeyPatch) -> None:
    cmd, _fake_client = command
    settings.django.last_updated_at = datetime(2026, 1, 1, 0, 0, 0)

    monkeypatch.setattr(
        cmd,
        "dynamic_import",
        lambda path: type("DjangoModel", (), {}) if path.startswith("repairshopr_data") else type("ApiModel", (), {}),
    )

    cmd.handle_model("repairshopr_data.models.user.User", "repairshopr_api.models.User", num_last_pages=1)


def test_handle_logs_timing_and_updates_last_updated_at(
    command,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cmd, fake_client = command
    start = datetime(2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 2, 1, 12, 1, 5, tzinfo=timezone.utc)
    tick = iter([start, end])

    monkeypatch.setattr(command_module, "now", lambda: next(tick))
    monkeypatch.setattr(cmd, "handle_model", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cmd, "sync_ticket_settings", lambda: None)

    saved_calls = {"count": 0}

    def fake_save() -> None:
        saved_calls["count"] += 1

    monkeypatch.setattr(settings, "save", fake_save)

    cmd.model_mapping = {"User": (None, None)}
    caplog.set_level(logging.INFO)

    cmd.handle()

    assert "SYNC_RUN start=2026-02-01T12:00:00+00:00" in caplog.text
    assert "SYNC_RUN done" in caplog.text
    assert "elapsed_seconds=65" in caplog.text
    assert settings.django.last_updated_at == start
    assert saved_calls["count"] == 1
    assert fake_client.cleared is True


def test_create_or_update_django_instance_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeManager:
        def __init__(self) -> None:
            self.store: dict[int, SimpleNamespace] = {}

        def update_or_create(self, defaults: dict, id: int):
            obj = self.store.get(id, SimpleNamespace(id=id))
            for key, value in defaults.items():
                setattr(obj, key, value)
            created = id not in self.store
            self.store[id] = obj
            return obj, created

    fake_manager = FakeManager()

    created_at_field = models.DateTimeField()
    created_at_field.name = "created_at"
    created_at_field.auto_created = False

    full_name_field = SimpleNamespace(name="full_name", auto_created=False)
    color_field = SimpleNamespace(name="color", auto_created=False)

    FakeDjangoModel = type(
        "FakeDjangoModel",
        (),
        {
            "_meta": SimpleNamespace(fields=[full_name_field, created_at_field, color_field]),
            "objects": fake_manager,
        },
    )

    api_instance = SimpleNamespace(
        id=501,
        full_name="First",
        created_at=datetime(2026, 2, 1, 10, 0, 0),
        color="blue",
    )
    create_or_update_django_instance(FakeDjangoModel, api_instance)

    api_instance.full_name = "Updated"
    api_instance.color = "green"
    create_or_update_django_instance(FakeDjangoModel, api_instance)

    assert len(fake_manager.store) == 1
    stored = fake_manager.store[501]
    assert stored.full_name == "Updated"
    assert stored.color == "green"


def test_create_or_update_django_instance_handles_foreign_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeForeignKey:
        def __init__(self, name: str, related_model) -> None:
            self.name = name
            self.related_model = related_model
            self.auto_created = False

    monkeypatch.setattr(command_module.models, "ForeignKey", FakeForeignKey)

    class FakeManager:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def update_or_create(self, defaults: dict, id: int):
            self.calls.append({"id": id, "defaults": defaults})
            return SimpleNamespace(id=id, **defaults), True

    related_manager = FakeManager()
    RelatedModel = type(
        "RelatedModel",
        (),
        {
            "_meta": SimpleNamespace(fields=[SimpleNamespace(name="name", auto_created=False)]),
            "objects": related_manager,
        },
    )

    parent_manager = FakeManager()
    created_at_field = models.DateTimeField()
    created_at_field.name = "created_at"
    created_at_field.auto_created = False
    owner_field = FakeForeignKey("owner", RelatedModel)

    ParentModel = type(
        "ParentModel",
        (),
        {
            "_meta": SimpleNamespace(fields=[created_at_field, owner_field]),
            "objects": parent_manager,
        },
    )

    api_instance = SimpleNamespace(
        id=10,
        created_at="2026-02-01T12:00:00Z",
        owner=SimpleNamespace(id=0, name="Owner Name"),
    )

    result = create_or_update_django_instance(ParentModel, api_instance, extra_fields={"extra": "value"})

    assert result.id == 10
    assert related_manager.calls[0]["id"] is None
    assert parent_manager.calls[0]["defaults"]["extra"] == "value"
    assert parent_manager.calls[0]["defaults"]["created_at"].tzinfo is not None


def test_create_or_update_django_instance_surfaces_data_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class ErrorManager:
        def update_or_create(self, defaults: dict, id: int):
            raise command_module.DataError("bad data")

    model_cls = type(
        "ErrorModel",
        (),
        {
            "_meta": SimpleNamespace(fields=[SimpleNamespace(name="name", auto_created=False)]),
            "objects": ErrorManager(),
        },
    )

    with pytest.raises(command_module.DataError):
        create_or_update_django_instance(model_cls, SimpleNamespace(id=1, name="x"))


def test_create_or_update_django_instance_surfaces_operational_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class ErrorManager:
        def update_or_create(self, defaults: dict, id: int):
            raise command_module.OperationalError("db down")

    model_cls = type(
        "ErrorModel",
        (),
        {
            "_meta": SimpleNamespace(fields=[SimpleNamespace(name="name", auto_created=False)]),
            "objects": ErrorManager(),
        },
    )

    with pytest.raises(command_module.OperationalError):
        create_or_update_django_instance(model_cls, SimpleNamespace(id=1, name="x"))


def test_get_submodel_class_and_dynamic_import(command, monkeypatch: pytest.MonkeyPatch) -> None:
    cmd, _ = command
    seen_paths: list[str] = []

    def fake_import(path: str):
        seen_paths.append(path)
        return object

    monkeypatch.setattr(cmd, "dynamic_import", fake_import)
    cmd.get_submodel_class("Ticket", "comments")
    cmd.get_submodel_class("Ticket", "properties")

    assert seen_paths[0].endswith("repairshopr_data.models.ticket.TicketComment")
    assert seen_paths[1].endswith("repairshopr_data.models.ticket.TicketProperties")

    imported = command_module.Command.dynamic_import("repairshopr_api.models.user.User")
    assert imported.__name__ == "User"


def test_handle_model_processes_related_submodels(command, monkeypatch: pytest.MonkeyPatch) -> None:
    cmd, fake_client = command
    settings.django.last_updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    set_calls: list[list] = []
    saved_children: list[int] = []

    class ParentCollection:
        def set(self, value):
            set_calls.append(value)

    parent_instance = SimpleNamespace(id=1, ticketcomments=ParentCollection())

    def fake_create_or_update(model_cls, api_instance, extra_fields=None):
        if model_cls.__name__ == "DjangoModel":
            return parent_instance

        child = SimpleNamespace(id=api_instance.id)

        def fake_save() -> None:
            saved_children.append(api_instance.id)

        child.save = fake_save
        return child

    monkeypatch.setattr(command_module, "create_or_update_django_instance", fake_create_or_update)

    class DjangoModel:
        __name__ = "Ticket"
        _meta = SimpleNamespace(
            related_objects=[SimpleNamespace(name="ticketcomments", field=SimpleNamespace(name="ticket"))]
        )

    class ApiModel:
        pass

    child_api_items = [SimpleNamespace(id=11), SimpleNamespace(id=12)]
    fake_client.get_model = lambda *_args, **_kwargs: [SimpleNamespace(id=1, ticketcomments=child_api_items)]

    monkeypatch.setattr(cmd, "dynamic_import", lambda path: DjangoModel if path.startswith("repairshopr_data") else ApiModel)
    monkeypatch.setattr(cmd, "get_submodel_class", lambda *_args, **_kwargs: type("SubModel", (), {}))

    cmd.handle_model("repairshopr_data.models.ticket.Ticket", "repairshopr_api.models.Ticket")

    assert saved_children == [11, 12]
    assert len(set_calls) == 1
    assert [item.id for item in set_calls[0]] == [11, 12]


def test_sync_ticket_settings_success_and_failure_paths(
    command,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cmd, _ = command

    class CaptureManager:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def update_or_create(self, **kwargs):
            self.calls.append(kwargs)

    type_manager = CaptureManager()
    field_manager = CaptureManager()
    answer_manager = CaptureManager()

    monkeypatch.setattr(command_module, "TicketType", SimpleNamespace(objects=type_manager))
    monkeypatch.setattr(command_module, "TicketTypeField", SimpleNamespace(objects=field_manager))
    monkeypatch.setattr(command_module, "TicketTypeFieldAnswer", SimpleNamespace(objects=answer_manager))

    cmd.client.fetch_ticket_settings = lambda: {
        "ticket_types": [{"id": 1, "name": "Repair"}],
        "ticket_type_fields": [
            {
                "id": 2,
                "name": "Device",
                "field_type": "text",
                "ticket_type_id": 1,
                "position": 1,
                "required": True,
            }
        ],
        "ticket_type_field_answers": [{"id": 3, "ticket_field_id": 2, "value": "Laptop"}],
    }
    cmd.sync_ticket_settings()

    assert len(type_manager.calls) == 1
    assert len(field_manager.calls) == 1
    assert len(answer_manager.calls) == 1

    caplog.set_level(logging.WARNING)
    cmd.client.fetch_ticket_settings = lambda: (_ for _ in ()).throw(RuntimeError("api down"))
    cmd.sync_ticket_settings()
    assert "Failed to fetch ticket settings" in caplog.text
