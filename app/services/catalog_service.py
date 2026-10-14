"""Service catalog and pricing rules: the single source of truth for prices.

The order form (frontend/dashboard.html) loads this through GET /catalog, the
order service uses the base fees, and the support agent quotes from it. Change
prices here and every consumer follows.
"""

from dataclasses import asdict, dataclass

SERVICE_TYPES = ("normal", "express")

BASE_FEE: dict[str, float] = {
    "normal": 500.0,
    "express": 900.0,
}

# Express applies this multiplier to every item price (base fee is separate).
EXPRESS_MULTIPLIER = 1.6

TURNAROUND: dict[str, str] = {
    "normal": "3 to 5 days",
    "express": "24 hours",
}

MAX_QUANTITY_PER_ITEM = 50


@dataclass(frozen=True)
class CatalogItem:
    id: str
    name: str
    emoji: str
    price: float  # normal-service price per item, in naira
    category: str


CATALOG: tuple[CatalogItem, ...] = (
    CatalogItem("shirt", "Shirt / Top", "👔", 150, "Tops"),
    CatalogItem("trouser", "Trouser / Jeans", "👖", 150, "Bottoms"),
    CatalogItem("dress", "Dress", "👗", 150, "Tops"),
    CatalogItem("suit_jacket", "Suit Jacket", "🧥", 200, "Formal"),
    CatalogItem("suit_trouser", "Suit Trouser", "👔", 200, "Formal"),
    CatalogItem("coat", "Coat / Jacket", "🧥", 250, "Outerwear"),
    CatalogItem("traditional", "Traditional Wear", "🥻", 200, "Traditional"),
    CatalogItem("ankara", "Ankara / Aso-Oke", "🧣", 250, "Traditional"),
    CatalogItem("wedding", "Wedding Dress", "👰", 500, "Specialty"),
    CatalogItem("kids", "Kids Wear", "👶", 100, "Kids"),
    CatalogItem("underwear", "Underwear / Socks", "🧦", 60, "Basics"),
    CatalogItem("sweater", "Sweater / Hoodie", "🧶", 180, "Outerwear"),
    CatalogItem("uniform", "Uniform (set)", "👕", 180, "Formal"),
    CatalogItem("bedsheet", "Bedsheet", "🛏️", 200, "Bedding"),
    CatalogItem("duvet", "Duvet / Comforter", "🛋️", 400, "Bedding"),
    CatalogItem("pillowcase", "Pillowcase", "🪫", 80, "Bedding"),
    CatalogItem("curtain", "Curtain (per panel)", "🪟", 300, "Home"),
)

_BY_ID = {item.id: item for item in CATALOG}


class QuoteError(ValueError):
    """Raised when a quote request references unknown items or bad values."""


@dataclass(frozen=True)
class QuoteLine:
    item_id: str
    name: str
    quantity: int
    unit_price: float
    subtotal: float


@dataclass(frozen=True)
class Quote:
    service_type: str
    lines: tuple[QuoteLine, ...]
    items_total: float
    base_fee: float
    total: float
    turnaround: str


def get_item(item_id: str) -> CatalogItem | None:
    return _BY_ID.get(item_id)


def unit_price(item: CatalogItem, service_type: str) -> float:
    if service_type == "express":
        # Matches the order form, which rounds to whole naira.
        return float(round(item.price * EXPRESS_MULTIPLIER))
    return float(item.price)


def calculate_quote(service_type: str, items: list[tuple[str, int]]) -> Quote:
    """Price a list of (item_id, quantity) pairs exactly as checkout would."""
    if service_type not in SERVICE_TYPES:
        raise QuoteError(f"Unknown service type: {service_type}")
    if not items:
        raise QuoteError("At least one item is required")

    lines = []
    for item_id, quantity in items:
        item = get_item(item_id)
        if item is None:
            raise QuoteError(f"Unknown item: {item_id}")
        if not 1 <= quantity <= MAX_QUANTITY_PER_ITEM:
            raise QuoteError(
                f"Quantity for {item_id} must be 1-{MAX_QUANTITY_PER_ITEM}"
            )
        price = unit_price(item, service_type)
        lines.append(
            QuoteLine(item.id, item.name, quantity, price, round(price * quantity, 2))
        )

    items_total = round(sum(line.subtotal for line in lines), 2)
    base_fee = BASE_FEE[service_type]
    return Quote(
        service_type=service_type,
        lines=tuple(lines),
        items_total=items_total,
        base_fee=base_fee,
        total=round(items_total + base_fee, 2),
        turnaround=TURNAROUND[service_type],
    )


def catalog_payload() -> dict:
    """Public catalog shape served at GET /catalog."""
    return {
        "currency": "NGN",
        "base_fee": BASE_FEE,
        "express_multiplier": EXPRESS_MULTIPLIER,
        "turnaround": TURNAROUND,
        "items": [asdict(item) for item in CATALOG],
    }
