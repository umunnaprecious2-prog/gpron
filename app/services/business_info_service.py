"""Verified Gpron business facts the support agent may state.

Prices come from catalog_service, never from here. Everything below mirrors
the public website (frontend/index.html footer, FAQ and pricing sections); if
the website copy changes, update this module in the same commit so the agent
does not drift from what customers see.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services.catalog_service import (
    BASE_FEE,
    CATALOG,
    EXPRESS_MULTIPLIER,
    TURNAROUND,
)

# Nigeria is UTC+1 all year (no daylight saving), so a fixed offset is exact
# and avoids needing tzdata on Windows dev machines.
LAGOS_TZ = timezone(timedelta(hours=1), "WAT")

CONTACT = {
    "email": "hello@gpron.ng",
    "phone": "+234 800 GPRON 1",
    "address": "Victoria Island, Lagos, Nigeria",
}


@dataclass(frozen=True)
class OpeningHours:
    label: str
    weekdays: tuple[int, ...]  # Monday=0
    opens: int  # hour, 24h clock
    closes: int


OPENING_HOURS: tuple[OpeningHours, ...] = (
    OpeningHours("Monday to Friday", (0, 1, 2, 3, 4), 8, 18),
    OpeningHours("Saturday", (5,), 9, 16),
    OpeningHours("Sunday", (6,), 10, 14),
)
HOURS_NOTES = "Closed on public holidays. Online orders can be placed 24/7."

ORDER_STATUSES = {
    "pending": "Order received and pending pickup",
    "picked_up": "Order picked up by our team",
    "in_cleaning": "Items are being cleaned",
    "ready": "Order is ready for delivery",
    "delivered": "Order delivered",
}

SERVICE_FEATURES = {
    "normal": [
        "Quality detergent included",
        "Fabric softener applied",
        "Folded and packaged",
        "Order tracking and status updates",
    ],
    "express": [
        "Priority processing queue",
        "Premium detergent and softener",
        "Steam ironed and pressed",
        "Real-time order tracking",
        "Express delivery included",
    ],
}

FAQ: tuple[tuple[str, str], ...] = (
    (
        "How do I place an order?",
        "Create a free account, log in to the dashboard, pick items from the "
        "catalog, choose Normal or Express, and submit. A GPRON tracking ID "
        "is issued immediately.",
    ),
    (
        "How do I track an order?",
        "Every order has a tracking ID like GPRON-2026-0001. Enter it on the "
        "Track Order page or check the dashboard. Stages: pending, picked up, "
        "in cleaning, ready, delivered.",
    ),
    (
        "Which fabrics and garments are handled?",
        "Cotton, linen, wool, silk and synthetic blends, plus delicate items "
        "such as wedding dresses, Ankara and Aso-Oke, suits and bedding.",
    ),
    (
        "Is my clothing safe?",
        "Every garment is inspected on arrival, handled by trained staff, "
        "tracked in the system, and cleaned with fabric-safe detergents.",
    ),
    (
        "Can I modify or cancel an order?",
        "Changes can be requested by contacting Gpron while the order is still "
        "Pending. Once picked up it moves through cleaning and cannot be "
        "cancelled. The assistant cannot change orders itself.",
    ),
    (
        "How do I pay?",
        "Payment is collected on delivery. There is no online payment yet.",
    ),
    (
        "How does pickup work?",
        "After an order is placed, the team collects garments from the "
        "customer's location. Specific pickup times are arranged by staff.",
    ),
)


def lagos_now(now_utc: datetime | None = None) -> datetime:
    now_utc = now_utc or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    return now_utc.astimezone(LAGOS_TZ)


def is_open(local: datetime) -> bool:
    for hours in OPENING_HOURS:
        if local.weekday() in hours.weekdays:
            return hours.opens <= local.hour < hours.closes
    return False


def render_knowledge(now_utc: datetime | None = None) -> str:
    """Compact fact sheet injected into the agent's system prompt."""
    local = lagos_now(now_utc)
    item_lines = "\n".join(
        f"- {item.id}: {item.name} = ₦{item.price:g} normal "
        f"(₦{round(item.price * EXPRESS_MULTIPLIER):g} express)"
        for item in CATALOG
    )
    hours = "; ".join(f"{h.label} {h.opens}:00-{h.closes}:00" for h in OPENING_HOURS)
    faq = "\n".join(f"- Q: {q}\n  A: {a}" for q, a in FAQ)
    statuses = ", ".join(f"{k} ({v})" for k, v in ORDER_STATUSES.items())
    features = "\n".join(
        f"- {svc}: " + "; ".join(items) for svc, items in SERVICE_FEATURES.items()
    )
    return f"""## Gpron facts (verified; the only facts you may state)
Business: Gpron Integrated Services, laundry and dry cleaning, Lagos, Nigeria.
Contact: phone {CONTACT['phone']}, email {CONTACT['email']}, office {CONTACT['address']}.
Opening hours (Lagos time): {hours}. {HOURS_NOTES}
Current Lagos time: {local:%A %d %B %Y, %H:%M}. The office is {'open' if is_open(local) else 'closed'} right now.

Services:
- normal: base fee ₦{BASE_FEE['normal']:g} per order + item prices, {TURNAROUND['normal']} turnaround
- express: base fee ₦{BASE_FEE['express']:g} per order + item prices x{EXPRESS_MULTIPLIER:g}, {TURNAROUND['express']} turnaround
Published service features:
{features}

Item prices per piece (item id: name = normal price (express price)):
{item_lines}
Items not in this list have no published price.

Order statuses: {statuses}.

FAQ and policies:
{faq}
"""
