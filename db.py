"""
data handling for the green-tech inventory assistant.
loads and persists inventory items to/from json.
uses batches for per-restock expiration tracking (fifo consumption).
"""

import json
from datetime import datetime
from pathlib import Path

INVENTORY_PATH = Path(__file__).parent / "inventory.json"
EXPIRED_LOG_PATH = Path(__file__).parent / "wall_of_shame.txt"


def _is_expired(expiration_date):
    if not expiration_date:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    return expiration_date < today


def log_expired(item_name, amount):
    """appends an expired-food entry to the wall of shame"""
    today = datetime.now().strftime("%Y-%m-%d")
    line = f"{today} | {item_name} -- {amount}\n"
    with open(EXPIRED_LOG_PATH, "a") as f:
        f.write(line)


def get_expired_log():
    """returns list of lines from the wall of shame, or empty list if file missing."""
    if not EXPIRED_LOG_PATH.exists():
        return []
    with open(EXPIRED_LOG_PATH, "r") as f:
        return [line.rstrip() for line in f if line.strip()]


def get_expired_batches_from_inventory():
    """scans inventory for expired batches. returns list of (item_name, amount) tuples."""
    items = load_inventory()
    result = []
    for item in items:
        name = item.get("name", "")
        for batch in item.get("batches", []):
            if _is_expired(batch.get("expiration_date")):
                result.append((name, batch["amount"]))
    return result


def sync_wall_of_shame_file():
    """overwrites wall_of_shame.txt with current expired batches from inventory."""
    expired = get_expired_batches_from_inventory()
    today = datetime.now().strftime("%Y-%m-%d")
    with open(EXPIRED_LOG_PATH, "w") as f:
        for name, amount in expired:
            f.write(f"{today} | {name} -- {amount}\n")


def _normalize_name(s):
    return s.strip().lower() if s else ""


def _find_item(items, name):
    name_norm = _normalize_name(name)
    for item in items:
        if _normalize_name(item.get("name", "")) == name_norm:
            return item
    return None


def _normalize_item(item):
    """
    ensures item conforms to schema: batches, unit, category.
    current_quantity is always derived from batches.
    """
    out = dict(item)
    out.setdefault("unit", "units")
    out.setdefault("category", "General")
    batches = out.get("batches", [])
    out["batches"] = batches
    out["current_quantity"] = sum(b["amount"] for b in batches)
    out.pop("quantity", None)
    out.pop("id", None)
    out.pop("usage_history", None)
    return out


def load_inventory():
    """returns full inventory from json. normalizes each item for schema compat."""
    if not INVENTORY_PATH.exists():
        return []
    with open(INVENTORY_PATH, "r") as f:
        items = json.load(f)
    return [_normalize_item(i) for i in items]


def save_inventory(items):
    """writes inventory to json."""
    with open(INVENTORY_PATH, "w") as f:
        json.dump(items, f, indent=2)


def add_item(name, quantity, date_added, predicted_expiration, unit="units", category="General"):
    """adds new item with initial batch """
    items = load_inventory()
    if not _normalize_name(name):
        raise ValueError("name cannot be empty")
    if _find_item(items, name):
        raise ValueError(f"item '{name}' already exists")   # names have to be unique
    today = datetime.now().strftime("%Y-%m-%d")
    batch = {"amount": quantity, "restocked_date": today, "expiration_date": predicted_expiration}
    item = {
        "name": name.strip(),
        "category": category,
        "current_quantity": quantity,
        "batches": [batch],
        "unit": unit,
        "date_added": date_added,
        "predicted_expiration": predicted_expiration,
    }
    items.append(item)
    save_inventory(items)
    return item


def record_usage(name, amount):
    """subtracts amount from batches (fifo), removes empty batches. logs expired batches to wall of shame."""
    items = load_inventory()
    item = _find_item(items, name)
    if not item:
        return None
    remaining = amount
    batches = item.setdefault("batches", [])
    while remaining > 0 and batches:
        batch = batches[0]
        take = min(remaining, batch["amount"])
        if take > 0 and _is_expired(batch.get("expiration_date")):
            log_expired(item["name"], take)
        batch["amount"] -= take
        remaining -= take
        if batch["amount"] <= 0:
            batches.pop(0)
    item["current_quantity"] = sum(b["amount"] for b in batches)
    save_inventory(items)
    return item


def record_restock(name, amount, expiration_date):
    """appends new batch."""
    items = load_inventory()
    item = _find_item(items, name)
    if not item:
        return None
    today = datetime.now().strftime("%Y-%m-%d")
    batch = {"amount": amount, "restocked_date": today, "expiration_date": expiration_date}
    item.setdefault("batches", []).append(batch)
    item["current_quantity"] = sum(b["amount"] for b in item["batches"])
    save_inventory(items)
    return item


def delete_batch(name, batch_number):
    """
    removes batch at 1-based index batch_number.
    if batch was expired, logs to wall of shame.
    returns updated item or None if item not found or batch_number invalid.
    """
    items = load_inventory()
    item = _find_item(items, name)
    if not item:
        return None
    batches = item.get("batches", [])
    if not batches or batch_number < 1 or batch_number > len(batches):
        return None
    batch = batches[batch_number - 1]
    if _is_expired(batch.get("expiration_date")):
        log_expired(item["name"], batch["amount"])
    batches.pop(batch_number - 1)
    item["current_quantity"] = sum(b["amount"] for b in batches)
    save_inventory(items)
    return item


def get_quantity(item):
    return item.get("current_quantity", 0)


def search_items(query):
    items = load_inventory()
    q = query.lower()
    return [i for i in items if q in i["name"].lower()]


def get_item_by_name(name):
    return _find_item(load_inventory(), name)


def load_inventory_sorted():
    return sorted(load_inventory(), key=lambda i: i["name"].lower())


def search_items_sorted(query):
    return sorted(search_items(query), key=lambda i: i["name"].lower())
