from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Mapping, TypedDict, TypeAlias, TypeGuard

import pytest
import requests
from django.db import models

from repairshopr_api.base.model import BaseModel
from repairshopr_api.config import settings
from repairshopr_data.management.commands import (
    import_from_repairshopr as command_module,
)
from repairshopr_data.management.commands.import_from_repairshopr import (
    _coerce_datetime,
    _instance_get_field,
    _instance_has_field,
    _parse_datetime,
    _resolve_related_collection,
    create_or_update_django_instance,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[
            tuple[type, datetime | None, int | None, dict[str, object] | None]
        ] = []
        self.cleared = False
        self.progress_callback = None

    def get_model(
        self,
        model: type,
        updated_at: datetime | None,
        num_last_pages: int | None,
        params: dict[str, object] | None,
    ) -> list[SimpleNamespace]:
        self.calls.append((model, updated_at, num_last_pages, params))
        return []

    def clear_cache(self) -> None:
        self.cleared = True

    def set_progress_callback(self, callback) -> None:  # type: ignore[no-untyped-def]
        self.progress_callback = callback

    @staticmethod
    def fetch_from_api(
        _model_name: str, params: dict[str, object] | None = None
    ) -> tuple[list[dict[str, object]], dict[str, int]]:
        if params and "invoice_id" in params:
            return [], {"total_pages": 1}
        return [], {"total_entries": 0, "total_pages": 1}

    @staticmethod
    def fetch_ticket_settings() -> dict[str, object]:
        return {}


CommandFixture: TypeAlias = tuple[command_module.Command, FakeClient]


class DummyApiModel(BaseModel):
    pass


class StoringManager:
    def __init__(self) -> None:
        self.store: dict[int, SimpleNamespace] = {}

    def update_or_create(
        self, defaults: dict[str, object], **lookup: object
    ) -> tuple[SimpleNamespace, bool]:
        instance_id = lookup.get("id")
        assert isinstance(instance_id, int)
        obj = self.store.get(instance_id, SimpleNamespace(id=instance_id))
        for key, value in defaults.items():
            setattr(obj, key, value)
        created = instance_id not in self.store
        self.store[instance_id] = obj
        return obj, created


class ForeignKeyUpdateCall(TypedDict):
    id: int | None
    defaults: dict[str, object]


class ForeignKeyTestManager:
    def __init__(self) -> None:
        self.calls: list[ForeignKeyUpdateCall] = []

    def update_or_create(
        self, defaults: dict[str, object], **lookup: object
    ) -> tuple[SimpleNamespace, bool]:
        lookup_id = lookup.get("id")
        assert lookup_id is None or isinstance(lookup_id, int)
        self.calls.append({"id": lookup_id, "defaults": defaults})
        return SimpleNamespace(id=lookup_id, **defaults), True


def _install_foreign_key_stub(monkeypatch: pytest.MonkeyPatch) -> type:
    class FakeForeignKey:
        def __init__(self, name: str, related_model: type) -> None:
            self.name = name
            self.related_model = related_model
            self.auto_created = False

    monkeypatch.setattr(command_module.models, "ForeignKey", FakeForeignKey)
    return FakeForeignKey


def set_simple_dynamic_import(
    monkeypatch: pytest.MonkeyPatch,
    cmd: command_module.Command,
    api_model: type[BaseModel] = DummyApiModel,
) -> None:
    django_model = type(
        "DjangoModel",
        (),
        {"_meta": SimpleNamespace(related_objects=[]), "objects": SimpleNamespace()},
    )
    monkeypatch.setattr(
        cmd,
        "dynamic_import",
        lambda path: django_model if path.startswith("repairshopr_data") else api_model,
    )


def is_django_model_type(candidate: type) -> TypeGuard[type[models.Model]]:
    return hasattr(candidate, "_meta") and hasattr(candidate, "objects")


def as_django_model_type(candidate: type) -> type[models.Model]:
    assert is_django_model_type(candidate)
    return candidate


def set_line_item_parity_counts(
    monkeypatch: pytest.MonkeyPatch,
    cmd: command_module.Command,
    *,
    expected_total: int,
    invoice_count: int,
    estimate_count: int,
) -> None:
    monkeypatch.setattr(
        cmd, "_fetch_line_item_total_entries", lambda _key: expected_total
    )
    monkeypatch.setattr(
        command_module,
        "InvoiceLineItem",
        SimpleNamespace(objects=SimpleNamespace(count=lambda: invoice_count)),
    )
    monkeypatch.setattr(
        command_module,
        "EstimateLineItem",
        SimpleNamespace(objects=SimpleNamespace(count=lambda: estimate_count)),
    )


def set_handle_model_imports_for_submodels(
    monkeypatch: pytest.MonkeyPatch,
    cmd: command_module.Command,
    django_model: type,
    api_model: type[BaseModel],
) -> None:
    monkeypatch.setattr(
        cmd,
        "dynamic_import",
        lambda path: django_model if path.startswith("repairshopr_data") else api_model,
    )
    monkeypatch.setattr(
        cmd, "get_submodel_class", lambda *_args, **_kwargs: type("SubModel", (), {})
    )


def setup_handle_model_test_state(
    command: CommandFixture,
    relation_name: str,
) -> tuple[
    command_module.Command,
    FakeClient,
    list[list[SimpleNamespace]],
    list[int],
    SimpleNamespace,
]:
    cmd, fake_client = command
    settings.django.last_updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    set_calls: list[list[SimpleNamespace]] = []
    saved_children: list[int] = []

    class ParentCollection:
        @staticmethod
        def set(value: list[SimpleNamespace]) -> None:
            set_calls.append(value)

    parent_instance = SimpleNamespace(id=1, **{relation_name: ParentCollection()})
    return cmd, fake_client, set_calls, saved_children, parent_instance


@pytest.fixture
def command(monkeypatch: pytest.MonkeyPatch) -> CommandFixture:
    fake_client = FakeClient()
    monkeypatch.setattr(command_module, "Client", lambda: fake_client)
    monkeypatch.setattr(
        command_module,
        "SyncStatus",
        SimpleNamespace(
            objects=SimpleNamespace(
                update_or_create=lambda **_kwargs: (SimpleNamespace(id=1), True)
            )
        ),
    )
    cmd = command_module.Command()
    return cmd, fake_client


def test_parse_datetime_and_coerce_datetime(caplog: pytest.LogCaptureFixture) -> None:
    parsed = _parse_datetime("2026-01-01T00:00:00Z", field_name="x")
    assert parsed == datetime(2026, 1, 1, tzinfo=timezone.utc)

    caplog.set_level(logging.WARNING)
    invalid = _parse_datetime("nope", field_name="x")
    assert invalid is None
    assert "Unable to parse datetime" in caplog.text

    assert _coerce_datetime(date(2026, 1, 2), field_name="x") == datetime(2026, 1, 2)
    assert _coerce_datetime("2026-01-03T00:00:00+00:00", field_name="x") == datetime(
        2026, 1, 3, tzinfo=timezone.utc
    )
    assert _coerce_datetime(1_704_067_200, field_name="x") == datetime(
        2024, 1, 1, tzinfo=timezone.utc
    )
    assert _coerce_datetime(object(), field_name="x") is None


def test_instance_has_field_avoids_triggering_computed_properties() -> None:
    property_reads = {"count": 0}

    class ApiInstanceWithExpensiveProperty:
        def __init__(self) -> None:
            self.id = 10

        @property
        def line_items(self) -> list[int]:
            property_reads["count"] += 1
            return [1, 2, 3]

    instance = ApiInstanceWithExpensiveProperty()

    assert _instance_has_field(instance, "id") is True
    assert _instance_has_field(instance, "line_items") is False
    assert property_reads["count"] == 0


def test_instance_field_helpers_do_not_fall_back_for_empty_values_mapping() -> None:
    empty_payload: Mapping[str, object] = {}
    assert _instance_has_field(empty_payload, "items") is False
    assert _instance_get_field(empty_payload, "items") is None

    populated_payload: Mapping[str, object] = {"items": [1, 2]}
    assert _instance_has_field(populated_payload, "items") is True
    assert _instance_get_field(populated_payload, "items") == [1, 2]

    property_reads = {"count": 0}

    class ApiInstanceWithOnlyProperty:
        @property
        def items(self) -> list[int]:
            property_reads["count"] += 1
            return [1]

    instance = ApiInstanceWithOnlyProperty()
    assert _instance_has_field(instance, "items") is False
    assert _instance_get_field(instance, "items") is None
    assert property_reads["count"] == 0


def test_resolve_related_collection_allows_line_items_property() -> None:
    calls = {"count": 0}

    class ApiInstanceWithLineItems:
        @property
        def line_items(self) -> list[dict[str, int]]:
            calls["count"] += 1
            return [{"id": 5}]

    class ApiInstanceWithOtherProperty:
        @property
        def comments(self) -> list[dict[str, int]]:
            calls["count"] += 1
            return [{"id": 6}]

    assert _resolve_related_collection(ApiInstanceWithLineItems(), "line_items") == [
        {"id": 5}
    ]
    assert _resolve_related_collection(ApiInstanceWithOtherProperty(), "comments") is None
    assert calls["count"] == 1


def test_handle_model_coerces_naive_last_updated_at(
    command: CommandFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    cmd, fake_client = command
    settings.django.last_updated_at = datetime(2026, 1, 1)

    set_simple_dynamic_import(monkeypatch, cmd)

    cmd.handle_model(
        "repairshopr_data.models.user.User",
        "repairshopr_api.models.User",
        num_last_pages=3,
    )

    _, updated_at_arg, num_last_pages_arg, _ = fake_client.calls[0]
    assert updated_at_arg is not None
    assert updated_at_arg.tzinfo is not None
    assert num_last_pages_arg == 3


def test_handle_model_uses_baseline_when_last_updated_is_too_old(
    command: CommandFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cmd, fake_client = command
    settings.django.last_updated_at = datetime(2000, 1, 1, tzinfo=timezone.utc)

    set_simple_dynamic_import(monkeypatch, cmd)

    cmd.handle_model(
        "repairshopr_data.models.user.User",
        "repairshopr_api.models.User",
        num_last_pages=8,
    )

    _, _, num_last_pages_arg, _ = fake_client.calls[0]
    assert num_last_pages_arg is None


def test_handle_model_naive_vs_aware_regression(
    command: CommandFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    cmd, _fake_client = command
    settings.django.last_updated_at = datetime(2026, 1, 1)

    set_simple_dynamic_import(monkeypatch, cmd)

    cmd.handle_model(
        "repairshopr_data.models.user.User",
        "repairshopr_api.models.User",
        num_last_pages=1,
    )


def test_handle_logs_timing_and_updates_last_updated_at(
    command: CommandFixture,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cmd, fake_client = command
    start = datetime(2026, 2, 1, 12, tzinfo=timezone.utc)
    end = datetime(2026, 2, 1, 12, 1, 5, tzinfo=timezone.utc)
    monkeypatch.setattr(command_module, "now", lambda: end)
    monkeypatch.setattr(cmd, "handle_model", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cmd, "sync_ticket_settings", lambda: None)
    monkeypatch.setattr(
        cmd,
        "validate_sync_completeness",
        lambda *_args, **_kwargs: None,
    )

    def fake_mark_started(*, full_sync: bool) -> None:
        _ = full_sync
        cmd._cycle_started_at = start

    monkeypatch.setattr(cmd, "_mark_sync_cycle_started", fake_mark_started)
    monkeypatch.setattr(cmd, "_mark_sync_cycle_finished", lambda **_kwargs: None)

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
    assert fake_client.progress_callback is None


def test_validate_sync_completeness_raises_for_full_sync_parity_mismatch(
    command: CommandFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    cmd, _ = command

    monkeypatch.setattr(
        cmd,
        "_fetch_line_item_total_entries",
        lambda filter_key: 10 if filter_key == "invoice_id_not_null" else 6,
    )
    monkeypatch.setattr(
        command_module,
        "InvoiceLineItem",
        SimpleNamespace(objects=SimpleNamespace(count=lambda: 200)),
    )
    monkeypatch.setattr(
        command_module,
        "EstimateLineItem",
        SimpleNamespace(objects=SimpleNamespace(count=lambda: 6)),
    )
    monkeypatch.setattr(
        cmd,
        "_evaluate_invoice_line_item_sample_parity",
        lambda *_args, **_kwargs: {
            "sample_size": 4,
            "mismatch_count": 0,
            "mismatches": [],
        },
    )

    with pytest.raises(RuntimeError, match="Sync completeness validation failed"):
        cmd.validate_sync_completeness(full_sync=True)


def test_validate_sync_completeness_warns_but_does_not_raise_for_incremental(
    command: CommandFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    cmd, _ = command

    set_line_item_parity_counts(
        monkeypatch,
        cmd,
        expected_total=100,
        invoice_count=20,
        estimate_count=20,
    )
    monkeypatch.setattr(
        cmd,
        "_evaluate_invoice_line_item_sample_parity",
        lambda *_args, **_kwargs: {
            "sample_size": 4,
            "mismatch_count": 4,
            "mismatches": [
                {"invoice_id": 1, "api_count": 5, "db_count": 1},
                {"invoice_id": 2, "api_count": 4, "db_count": 2},
            ],
        },
    )

    cmd.validate_sync_completeness(full_sync=False)


def test_validate_sync_completeness_does_not_raise_for_incremental_sample_errors(
    command: CommandFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    cmd, _ = command

    set_line_item_parity_counts(
        monkeypatch,
        cmd,
        expected_total=100,
        invoice_count=100,
        estimate_count=100,
    )
    monkeypatch.setattr(
        cmd,
        "_evaluate_invoice_line_item_sample_parity",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            requests.RequestException("sample broke")
        ),
    )

    cmd.validate_sync_completeness(full_sync=False)


def test_validate_sync_completeness_raises_for_unexpected_incremental_sample_errors(
    command: CommandFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    cmd, _ = command

    set_line_item_parity_counts(
        monkeypatch,
        cmd,
        expected_total=100,
        invoice_count=100,
        estimate_count=100,
    )
    monkeypatch.setattr(
        cmd,
        "_evaluate_invoice_line_item_sample_parity",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bug")),
    )

    with pytest.raises(RuntimeError, match="bug"):
        cmd.validate_sync_completeness(full_sync=False)


def test_create_or_update_django_instance_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_manager = StoringManager()

    created_at_field = models.DateTimeField()
    created_at_field.name = "created_at"
    created_at_field.auto_created = False

    full_name_field = SimpleNamespace(name="full_name", auto_created=False)
    color_field = SimpleNamespace(name="color", auto_created=False)

    fake_django_model_cls = type(
        "FakeDjangoModel",
        (),
        {
            "_meta": SimpleNamespace(
                fields=[full_name_field, created_at_field, color_field]
            ),
            "objects": fake_manager,
        },
    )

    api_instance = SimpleNamespace(
        id=501,
        full_name="First",
        created_at=datetime(2026, 2, 1, 10),
        color="blue",
    )
    create_or_update_django_instance(
        as_django_model_type(fake_django_model_cls), api_instance
    )

    api_instance.full_name = "Updated"
    api_instance.color = "green"
    create_or_update_django_instance(
        as_django_model_type(fake_django_model_cls), api_instance
    )

    assert len(fake_manager.store) == 1
    stored = fake_manager.store[501]
    assert stored.full_name == "Updated"
    assert stored.color == "green"


def test_create_or_update_django_instance_coerces_blank_integer_fields_to_none() -> (
    None
):
    fake_manager = StoringManager()

    type_field = models.IntegerField(null=True)
    type_field.name = "type"
    type_field.auto_created = False

    model_cls = type(
        "CustomerProperties",
        (),
        {
            "_meta": SimpleNamespace(fields=[type_field]),
            "objects": fake_manager,
        },
    )

    create_or_update_django_instance(
        as_django_model_type(model_cls), SimpleNamespace(id=42, type="")
    )

    assert fake_manager.store[42].type is None


def test_create_or_update_django_instance_accepts_mapping_payload() -> None:
    fake_manager = StoringManager()

    full_name_field = SimpleNamespace(name="full_name", auto_created=False)
    model_cls = type(
        "Customer",
        (),
        {
            "_meta": SimpleNamespace(fields=[full_name_field]),
            "objects": fake_manager,
        },
    )

    create_or_update_django_instance(
        as_django_model_type(model_cls), {"id": "77", "full_name": "Mapped Name"}
    )

    assert fake_manager.store[77].full_name == "Mapped Name"


def test_create_or_update_django_instance_handles_foreign_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_foreign_key = _install_foreign_key_stub(monkeypatch)

    related_manager = ForeignKeyTestManager()
    related_model_cls = type(
        "RelatedModel",
        (),
        {
            "_meta": SimpleNamespace(
                fields=[SimpleNamespace(name="name", auto_created=False)]
            ),
            "objects": related_manager,
        },
    )

    parent_manager = ForeignKeyTestManager()
    created_at_field = models.DateTimeField()
    created_at_field.name = "created_at"
    created_at_field.auto_created = False
    owner_field = fake_foreign_key("owner", related_model_cls)

    parent_model_cls = type(
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

    result = create_or_update_django_instance(
        as_django_model_type(parent_model_cls),
        api_instance,
        extra_fields={"extra": "value"},
    )

    assert getattr(result, "id", None) == 10
    assert related_manager.calls[0]["id"] is None
    parent_defaults = parent_manager.calls[0]["defaults"]
    assert parent_defaults["extra"] == "value"
    created_at = parent_defaults["created_at"]
    assert isinstance(created_at, datetime)
    assert created_at.tzinfo is not None


def test_create_or_update_django_instance_handles_mapping_foreign_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_foreign_key = _install_foreign_key_stub(monkeypatch)

    related_manager = ForeignKeyTestManager()
    related_model_cls = type(
        "RelatedModel",
        (),
        {
            "_meta": SimpleNamespace(
                fields=[SimpleNamespace(name="name", auto_created=False)]
            ),
            "objects": related_manager,
        },
    )

    parent_manager = ForeignKeyTestManager()
    owner_field = fake_foreign_key("owner", related_model_cls)
    parent_model_cls = type(
        "ParentModel",
        (),
        {
            "_meta": SimpleNamespace(
                fields=[SimpleNamespace(name="status", auto_created=False), owner_field]
            ),
            "objects": parent_manager,
        },
    )

    parent_payload = {
        "id": "101",
        "status": "open",
        "owner": {"id": "9", "name": "Owner"},
    }

    result = create_or_update_django_instance(
        as_django_model_type(parent_model_cls), parent_payload
    )

    assert getattr(result, "id", None) == 101
    assert related_manager.calls[0]["id"] == 9


def test_create_or_update_django_instance_surfaces_data_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ErrorManager:
        @staticmethod
        def update_or_create(
            defaults: dict[str, object], **_lookup: object
        ) -> tuple[SimpleNamespace, bool]:
            _ = defaults
            raise command_module.DataError("bad data")

    model_cls = type(
        "ErrorModel",
        (),
        {
            "_meta": SimpleNamespace(
                fields=[SimpleNamespace(name="name", auto_created=False)]
            ),
            "objects": ErrorManager(),
        },
    )

    with pytest.raises(command_module.DataError):
        create_or_update_django_instance(
            as_django_model_type(model_cls), SimpleNamespace(id=1, name="x")
        )


def test_create_or_update_django_instance_surfaces_operational_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ErrorManager:
        @staticmethod
        def update_or_create(
            defaults: dict[str, object], **_lookup: object
        ) -> tuple[SimpleNamespace, bool]:
            _ = defaults
            raise command_module.OperationalError("db down")

    model_cls = type(
        "ErrorModel",
        (),
        {
            "_meta": SimpleNamespace(
                fields=[SimpleNamespace(name="name", auto_created=False)]
            ),
            "objects": ErrorManager(),
        },
    )

    with pytest.raises(command_module.OperationalError):
        create_or_update_django_instance(
            as_django_model_type(model_cls), SimpleNamespace(id=1, name="x")
        )


def test_get_submodel_class_and_dynamic_import(
    command: CommandFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    cmd, _ = command
    seen_paths: list[str] = []

    def fake_import(path: str) -> type:
        seen_paths.append(path)
        return type(
            "FakeSubModel",
            (),
            {
                "_meta": SimpleNamespace(related_objects=[]),
                "objects": SimpleNamespace(),
            },
        )

    monkeypatch.setattr(cmd, "dynamic_import", fake_import)
    cmd.get_submodel_class("Ticket", "comments")
    cmd.get_submodel_class("Ticket", "properties")

    assert seen_paths[0].endswith("repairshopr_data.models.ticket.TicketComment")
    assert seen_paths[1].endswith("repairshopr_data.models.ticket.TicketProperties")

    imported = command_module.Command.dynamic_import("repairshopr_api.models.user.User")
    assert imported.__name__ == "User"


def test_handle_model_processes_related_submodels(
    command: CommandFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    cmd, fake_client, set_calls, saved_children, parent_instance = (
        setup_handle_model_test_state(command, "ticketcomments")
    )

    def fake_create_or_update(
        model_cls: type[models.Model],
        api_instance: SimpleNamespace,
        extra_fields: Mapping[str, object] | None = None,
    ) -> SimpleNamespace:
        _ = extra_fields
        if model_cls.__name__ == "DjangoModel":
            return parent_instance

        child = SimpleNamespace(id=api_instance.id)

        def fake_save() -> None:
            saved_children.append(api_instance.id)

        child.save = fake_save
        return child

    monkeypatch.setattr(
        command_module, "create_or_update_django_instance", fake_create_or_update
    )

    class DjangoModel:
        __name__ = "Ticket"
        _meta = SimpleNamespace(
            related_objects=[
                SimpleNamespace(
                    name="ticketcomments", field=SimpleNamespace(name="ticket")
                )
            ]
        )
        objects = SimpleNamespace()

    class ApiModel(BaseModel):
        pass

    child_api_items = [SimpleNamespace(id=11), SimpleNamespace(id=12)]
    fake_client.get_model = lambda *_args, **_kwargs: [
        SimpleNamespace(id=1, ticketcomments=child_api_items)
    ]

    set_handle_model_imports_for_submodels(monkeypatch, cmd, DjangoModel, ApiModel)

    cmd.handle_model(
        "repairshopr_data.models.ticket.Ticket", "repairshopr_api.models.Ticket"
    )

    assert saved_children == [11, 12]
    assert len(set_calls) == 1
    assert [item.id for item in set_calls[0]] == [11, 12]


def test_handle_model_processes_line_items_from_property(
    command: CommandFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    cmd, fake_client, set_calls, saved_children, parent_instance = (
        setup_handle_model_test_state(command, "line_items")
    )

    def fake_create_or_update(
        model_cls: type[models.Model],
        api_instance: object,
        extra_fields: Mapping[str, object] | None = None,
    ) -> SimpleNamespace:
        _ = extra_fields
        if model_cls.__name__ == "DjangoModel":
            return parent_instance

        item_id = int(getattr(api_instance, "id", 0))
        child = SimpleNamespace(id=item_id)

        def fake_save() -> None:
            saved_children.append(item_id)

        child.save = fake_save
        return child

    monkeypatch.setattr(
        command_module, "create_or_update_django_instance", fake_create_or_update
    )

    class DjangoModel:
        __name__ = "Invoice"
        _meta = SimpleNamespace(
            related_objects=[
                SimpleNamespace(name="line_items", field=SimpleNamespace(name="parent_invoice"))
            ]
        )
        objects = SimpleNamespace()

    class ApiModel(BaseModel):
        @property
        def line_items(self) -> list[SimpleNamespace]:
            return [SimpleNamespace(id=21), SimpleNamespace(id=22)]

    fake_client.get_model = lambda *_args, **_kwargs: [ApiModel(id=1)]

    set_handle_model_imports_for_submodels(monkeypatch, cmd, DjangoModel, ApiModel)

    cmd.handle_model(
        "repairshopr_data.models.invoice.Invoice", "repairshopr_api.models.Invoice"
    )

    assert saved_children == [21, 22]
    assert len(set_calls) == 1
    assert [item.id for item in set_calls[0]] == [21, 22]


def test_sync_ticket_settings_success_and_failure_paths(
    command: CommandFixture,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cmd, _ = command

    class CaptureManager:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def update_or_create(self, **kwargs: object) -> None:
            self.calls.append(kwargs)

    type_manager = CaptureManager()
    field_manager = CaptureManager()
    answer_manager = CaptureManager()

    monkeypatch.setattr(
        command_module, "TicketType", SimpleNamespace(objects=type_manager)
    )
    monkeypatch.setattr(
        command_module, "TicketTypeField", SimpleNamespace(objects=field_manager)
    )
    monkeypatch.setattr(
        command_module, "TicketTypeFieldAnswer", SimpleNamespace(objects=answer_manager)
    )

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
        "ticket_type_field_answers": [
            {"id": 3, "ticket_field_id": 2, "value": "Laptop"}
        ],
    }
    cmd.sync_ticket_settings()

    assert len(type_manager.calls) == 1
    assert len(field_manager.calls) == 1
    assert len(answer_manager.calls) == 1

    caplog.set_level(logging.WARNING)
    cmd.client.fetch_ticket_settings = lambda: (_ for _ in ()).throw(ValueError("api down"))
    cmd.sync_ticket_settings()
    assert "Failed to fetch ticket settings" in caplog.text
