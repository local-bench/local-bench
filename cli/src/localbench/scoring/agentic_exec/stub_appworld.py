"""Hermetic AppWorld-like fixture for agentic harness tests."""

from __future__ import annotations

from dataclasses import dataclass, replace

from localbench._types import JsonObject, JsonValue


class StubToolError(Exception):
    """Raised when the stub receives invalid API arguments."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class StubTaskSpec:
    """Metadata shape mirrored from real AppWorld tasks."""

    task_id: str
    instruction: str
    family: str
    band: str
    allowed_tools: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ApiCall:
    """One API call observed by the stub."""

    tool: str
    arguments: JsonObject


@dataclass(frozen=True, slots=True)
class OrderRecord:
    """Minimal order state for the stub apps."""

    order_id: str
    customer_id: str
    total: float
    status: str
    refunded: bool = False
    refund_reason: str | None = None


@dataclass(frozen=True, slots=True)
class UserRecord:
    """Minimal CRM state for cross-app tasks."""

    user_id: str
    name: str
    email: str
    vip: bool


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    """Created calendar event record."""

    user_id: str
    title: str
    day: str


@dataclass(frozen=True, slots=True)
class SentEmail:
    """Sent email record."""

    user_id: str
    subject: str
    body: str


@dataclass(frozen=True, slots=True)
class StubEvalResult:
    """Final-state verifier result shaped like AppWorld eval output."""

    passed: bool
    collateral_damage: bool
    checks: JsonObject


class StubAppWorld:
    """Mutable hermetic AppWorld-like state used only by local unit tests."""

    def __init__(self) -> None:
        self._tasks = _build_tasks()
        self._orders: dict[str, OrderRecord] = {
            "o-100": OrderRecord(
                order_id="o-100",
                customer_id="u-1",
                total=12.3456789,
                status="paid",
            ),
        }
        self._users: dict[str, UserRecord] = {
            "u-1": UserRecord(user_id="u-1", name="Alex Chen", email="alex@example.test", vip=False),
            "u-2": UserRecord(user_id="u-2", name="Priya Shah", email="priya@example.test", vip=True),
        }
        self._events: list[CalendarEvent] = []
        self._emails: list[SentEmail] = []
        self.api_call_log: list[ApiCall] = []
        self._collateral_damage = False

    def task_ids(self) -> tuple[str, ...]:
        """Return deterministic fixture task ids."""
        return tuple(sorted(self._tasks))

    def load_task(self, task_id: str) -> StubTaskSpec:
        """Load one stub task by id."""
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise StubToolError(f"unknown task id: {task_id}") from exc

    def call_api(self, tool: str, arguments: JsonObject) -> JsonValue:
        """Dispatch a stub API call after the adapter's whitelist check."""
        self.api_call_log.append(ApiCall(tool=tool, arguments=dict(arguments)))
        match tool:  # noqa: MATCH_OK - stub API surface rejects unknown tool names.
            case "orders.get_order":
                return self._get_order(arguments)
            case "orders.refund_order":
                return self._refund_order(arguments)
            case "crm.get_user":
                return self._get_user(arguments)
            case "calendar.create_event":
                return self._create_event(arguments)
            case "mail.send_email":
                return self._send_email(arguments)
            case _:
                raise StubToolError(f"unknown API: {tool}")

    def verify(self, task_id: str, answer: JsonValue) -> StubEvalResult:
        """Evaluate final state for a stub task."""
        match task_id:  # noqa: MATCH_OK - stub verifier rejects unknown task ids.
            case "stub_read_order_total":
                passed = answer == {"order_id": "o-100", "total": 12.3457}
                checks = {"answer_matches_order_total": passed}
            case "stub_refund_paid_order":
                order = self._orders["o-100"]
                passed = order.refunded and order.refund_reason == "duplicate"
                checks = {"order_refunded": passed}
            case "stub_schedule_vip_followup":
                passed = self._has_followup_event("u-2") and self._has_followup_email("u-2")
                checks = {"vip_event_and_email_created": passed}
            case _:
                raise StubToolError(f"unknown task id: {task_id}")
        return StubEvalResult(
            passed=passed and not self._collateral_damage,
            collateral_damage=self._collateral_damage,
            checks=checks,
        )

    def _get_order(self, arguments: JsonObject) -> JsonValue:
        order_id = _require_string(arguments, "order_id")
        return {"order": _order_json(self._orders[order_id])}

    def _refund_order(self, arguments: JsonObject) -> JsonValue:
        order_id = _require_string(arguments, "order_id")
        reason = _require_string(arguments, "reason")
        if order_id != "o-100":
            self._collateral_damage = True
        order = self._orders[order_id]
        self._orders[order_id] = replace(order, refunded=True, refund_reason=reason)
        return {"order_id": order_id, "refunded": True}

    def _get_user(self, arguments: JsonObject) -> JsonValue:
        user_id = _require_string(arguments, "user_id")
        return {"user": _user_json(self._users[user_id])}

    def _create_event(self, arguments: JsonObject) -> JsonValue:
        event = CalendarEvent(
            user_id=_require_string(arguments, "user_id"),
            title=_require_string(arguments, "title"),
            day=_require_string(arguments, "day"),
        )
        if event.user_id != "u-2":
            self._collateral_damage = True
        self._events.append(event)
        return {"event": _event_json(event)}

    def _send_email(self, arguments: JsonObject) -> JsonValue:
        email = SentEmail(
            user_id=_require_string(arguments, "user_id"),
            subject=_require_string(arguments, "subject"),
            body=_require_string(arguments, "body"),
        )
        if email.user_id != "u-2":
            self._collateral_damage = True
        self._emails.append(email)
        return {"email": _email_json(email)}

    def _has_followup_event(self, user_id: str) -> bool:
        return any(event.user_id == user_id and event.title == "VIP follow-up" for event in self._events)

    def _has_followup_email(self, user_id: str) -> bool:
        return any(email.user_id == user_id and email.subject == "VIP follow-up scheduled" for email in self._emails)


def build_stub_appworld() -> StubAppWorld:
    """Build a fresh stub world for a single hermetic test/run."""
    # SEAM: real AppWorld environment construction wires in here.
    return StubAppWorld()


def _build_tasks() -> dict[str, StubTaskSpec]:
    return {
        "stub_read_order_total": StubTaskSpec(
            task_id="stub_read_order_total",
            instruction="Look up order o-100 and report its total.",
            family="read_lookup_exact_answer",
            band="appworld_level_1",
            allowed_tools=("orders.get_order",),
        ),
        "stub_refund_paid_order": StubTaskSpec(
            task_id="stub_refund_paid_order",
            instruction="Refund paid order o-100 for duplicate purchase.",
            family="single_app_state_mutation",
            band="appworld_level_1",
            allowed_tools=("orders.get_order", "orders.refund_order"),
        ),
        "stub_schedule_vip_followup": StubTaskSpec(
            task_id="stub_schedule_vip_followup",
            instruction="Create a VIP follow-up event and notification for user u-2.",
            family="cross_app_workflow",
            band="appworld_level_2",
            allowed_tools=("crm.get_user", "calendar.create_event", "mail.send_email"),
        ),
    }


def _require_string(arguments: JsonObject, key: str) -> str:
    match arguments.get(key):  # noqa: MATCH_OK - decoded JSON field is open input.
        case str() as value:
            return value
        case _:
            raise StubToolError(f"{key} must be a string")


def _order_json(order: OrderRecord) -> JsonObject:
    return {
        "id": order.order_id,
        "customer_id": order.customer_id,
        "total": order.total,
        "status": order.status,
        "refunded": order.refunded,
    }


def _user_json(user: UserRecord) -> JsonObject:
    return {
        "id": user.user_id,
        "name": user.name,
        "email": user.email,
        "vip": user.vip,
    }


def _event_json(event: CalendarEvent) -> JsonObject:
    return {"user_id": event.user_id, "title": event.title, "day": event.day}


def _email_json(email: SentEmail) -> JsonObject:
    return {"user_id": email.user_id, "subject": email.subject, "body": email.body}
