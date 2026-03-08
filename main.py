"""
cli routing for the green-tech inventory assistant.
handles user commands: add, view, update, search.
"""

import sys
from datetime import datetime

from db import (
    add_item as db_add_item,
    delete_batch,
    get_expired_batches_from_inventory,
    get_item_by_name,
    get_quantity,
    load_inventory_sorted,
    record_restock,
    record_usage,
    search_items_sorted,
    sync_wall_of_shame_file,
)
from ai_service import (
    compute_predicted_expiration,
    predict_shelf_life_days,
)

BOLD = "\033[1m"
RED = "\033[91m"
YELLOW = "\033[93m"
WHITE = "\033[97m"
RESET = "\033[0m"

MIN_COL_NAME = 10
MIN_COL_QTY = 6
MIN_COL_EXPIRES = 12


def days_until_expiration(predicted_expiration):
    """ computes days remaining until predicted_expiration from today """
    today = datetime.now().date()
    exp = datetime.strptime(predicted_expiration, "%Y-%m-%d").date()
    return (exp - today).days


def _format_expires(days):
    """returns display string for days until expiration."""
    if days <= 0:
        return f"EXPIRED {-days} DAYS AGO"
    elif days <= 3:
        return f"EXPIRES IN {days} DAYS"
    return f"expires in {days} days"


def _format_batches_expires(item):
    """
    returns multi-line string of batch expiration status.
    each batch: "batch N: EXPIRED X DAYS AGO" or "batch N: expires in X days"
    """
    batches = item.get("batches", [])
    if not batches:
        return "no batches"
    lines = []
    for i, batch in enumerate(batches, 1):
        exp = batch.get("expiration_date")
        if not exp:
            lines.append(f"batch {i}: unknown")
            continue
        days = days_until_expiration(exp)
        lines.append(f"batch {i}: {_format_expires(days)}")
    return "\n".join(lines)


def _format_batches_for_delete(item):
    """returns multi-line string of batches with amount for delete-batch flow."""
    batches = item.get("batches", [])
    if not batches:
        return []
    lines = []
    for i, batch in enumerate(batches, 1):
        amt = batch.get("amount", 0)
        exp = batch.get("expiration_date", "?")
        days = days_until_expiration(exp) if exp != "?" else "?"
        status = _format_expires(days) if days != "?" else "unknown"
        lines.append(f"  {i}. {amt} units — {status}")
    return lines


def _has_expired_or_warning(expires_str):
    """returns (has_expired, has_warning) for coloring."""
    has_exp = "EXPIRED" in expires_str
    has_warn = "EXPIRES IN" in expires_str and not has_exp
    return has_exp, has_warn


def _compute_column_widths(headers, rows, mins):
    """computes column widths. for multi-line cells, uses max line length."""
    widths = []
    for col, min_w in enumerate(mins):
        header_len = len(str(headers[col]))
        max_cell = 0
        for r in rows:
            val = str(r[col])
            for line in val.split("\n"):
                max_cell = max(max_cell, len(line))
        widths.append(max(min_w, header_len, max_cell))
    return widths


def _print_table(headers, rows, color_fn=None):
    """
    prints a boxed table with aligned columns
    headers: list of header strings. rows: list of tuples (same length as headers)
    color_fn(row_index, line_index, is_expired, is_warning) for per-line coloring
    """
    mins = [MIN_COL_NAME, MIN_COL_QTY, MIN_COL_EXPIRES]
    widths = _compute_column_widths(headers, rows, mins)

    def border():
        parts = "┬".join("─" * w for w in widths)
        return f"{WHITE}┌{parts}┐{RESET}"

    def row_sep():
        parts = "┼".join("─" * w for w in widths)
        return f"{WHITE}├{parts}┤{RESET}"

    def bottom():
        parts = "┴".join("─" * w for w in widths)
        return f"{WHITE}└{parts}┘{RESET}"

    def pipe():
        return f"{WHITE}│{RESET}"

    def fmt_cell_line(s, j, w):
        s = (s[: w - 1] + "…") if len(s) > w else s
        if j == 1:
            return s.center(w)
        return s.ljust(w)

    print(border())
    header_cells = [fmt_cell_line(str(h), j, w) for j, (h, w) in enumerate(zip(headers, widths))]
    print(f"{pipe()}{pipe().join(header_cells)}{pipe()}")
    print(row_sep())

    for i, row in enumerate(rows):
        col_vals = [str(row[j]) for j in range(len(row))]
        expires_lines = (col_vals[2] if len(col_vals) > 2 else "").split("\n")

        cell_lines = [col_vals[j].split("\n") for j in range(len(col_vals))]
        row_height = max(len(lines) for lines in cell_lines)

        for line_idx in range(row_height):
            expires_line = expires_lines[line_idx] if line_idx < len(expires_lines) else ""
            prefix, suffix = "", ""
            if color_fn:
                is_exp, is_warn = _has_expired_or_warning(expires_line)
                codes = color_fn(i, line_idx, is_exp, is_warn)
                if codes:
                    prefix, suffix = codes

            cells = []
            for j, w in enumerate(widths):
                lines = cell_lines[j] if j < len(cell_lines) else []
                line_content = lines[line_idx] if line_idx < len(lines) else ""
                cell = fmt_cell_line(line_content, j, w)
                cells.append(f"{prefix}{cell}{suffix}" if prefix else cell)
            print(f"{pipe()}{pipe().join(cells)}{pipe()}")

        if i < len(rows) - 1:
            print(row_sep())

    print(bottom())


def view_items():
    """
    lists all inventory items and shows days remaining
    sorted by name in a table format with colored warnings
    """
    items = load_inventory_sorted()
    if not items:
        print("No items in inventory.")
        return

    headers = ["Name", "Qty", "Expires"]
    rows = []
    for item in items:
        expires_str = _format_batches_expires(item)
        rows.append((item["name"], get_quantity(item), expires_str))

    def color_fn(_, __, is_expired, is_warning):
        if is_expired:
            return (f"{BOLD}{RED}", RESET)
        if is_warning:
            return (f"{BOLD}{YELLOW}", RESET)
        return (WHITE, RESET)

    _print_table(headers, rows, color_fn)


def add_item():
    """
    prompts for name and quantity
    predicts shelf life via ai
    adds the item with today as date_added
    """
    name = input("Item name: ").strip()
    if not name:
        print("Name cannot be empty.")
        return

    qty_str = input("Quantity: ").strip()
    try:
        quantity = int(qty_str)
        if(quantity < 0):
            print("Quantity cannot be negative.")
            return
    except ValueError:
        print("Quantity must be an integer.")
        return

    shelf_days, is_estimated = predict_shelf_life_days(name)
    if is_estimated:
        print(f"  Shelf life: {shelf_days} days (Estimated)")

    today = datetime.now().strftime("%Y-%m-%d")
    predicted_expiration = compute_predicted_expiration(today, shelf_days)

    try:
        item = db_add_item(name, quantity, today, predicted_expiration)
        print(f"Added: {item['name']} | expires {predicted_expiration}")
    except ValueError as e:
        print(str(e))


def update_item():
    """
    prompts for item name, action (restock or use), and amount
    updates current_quantity and batches accordingly
    """
    name = input("Item name: ").strip()
    if not name:
        print("Name cannot be empty.")
        return

    action_str = input("Restock or use? (r/u): ").strip().lower()
    if action_str not in ("r", "u"):
        print("Enter 'r' for restock or 'u' for use.")
        return

    amt_str = input("Amount: ").strip()
    try:
        amount = int(amt_str)
    except ValueError:
        print("Amount must be an integer.")
        return

    if amount < 0:
        print("Amount cannot be negative.")
        return

    if action_str == "r":
        shelf_days, is_estimated = predict_shelf_life_days(name)
        if is_estimated:
            print(f"  Shelf life: {shelf_days} days (Estimated)")
        today = datetime.now().strftime("%Y-%m-%d")
        expiration_date = compute_predicted_expiration(today, shelf_days)
        updated = record_restock(name, amount, expiration_date)
        if updated:
            print(f"Recorded restock of {amount} for {updated['name']}. New total: {updated['current_quantity']}")
    else:
        updated = record_usage(name, amount)
        if updated:
            print(f"Recorded {amount} used for {updated['name']}. Remaining: {updated['current_quantity']}")

    if not updated:
        print("Item not found.")


def search_item():
    """ prompts for search query and lists matching items in table format """
    query = input("Search by name: ").strip()
    if not query:
        print("Enter a search term.")
        return

    matches = search_items_sorted(query)
    if not matches:
        print("No matching items.")
        return

    headers = ["Name", "Qty", "Expires"]
    rows = []
    for item in matches:
        expires_str = _format_batches_expires(item)
        rows.append((item["name"], get_quantity(item), expires_str))

    def color_fn(_, __, is_expired, is_warning):
        if is_expired:
            return (f"{BOLD}{RED}", RESET)
        if is_warning:
            return (f"{BOLD}{YELLOW}", RESET)
        return (WHITE, RESET)

    _print_table(headers, rows, color_fn)


def delete_batch_item():
    """
    prompts for item name (search), shows batches, then deletes selected batch.
    use case: remove expired batch (e.g. batch 1 of Bread) from inventory.
    """
    query = input("Search item by name: ").strip()
    if not query:
        print("Enter a search term.")
        return

    matches = search_items_sorted(query)
    if not matches:
        print("No matching items.")
        return

    if len(matches) > 1:
        print("Matches:")
        for m in matches:
            print(f"  - {m['name']}")
        name = input("Enter exact item name: ").strip()
    else:
        name = matches[0]["name"]

    item = get_item_by_name(name)
    if not item:
        print("Item not found.")
        return

    batches = item.get("batches", [])
    if not batches:
        print(f"{name} has no batches.")
        return

    print(f"\n{name} — batches:")
    for line in _format_batches_for_delete(item):
        print(line)

    num_str = input(f"\nBatch number to delete (1-{len(batches)}): ").strip()
    try:
        batch_num = int(num_str)
    except ValueError:
        print("Enter a number.")
        return

    if batch_num < 1 or batch_num > len(batches):
        print(f"Invalid. Enter 1-{len(batches)}.")
        return

    confirm = input("Delete this batch? (y/n): ").strip().lower()
    if confirm != "y":
        print("Cancelled.")
        return

    updated = delete_batch(name, batch_num)
    if updated:
        print(f"Deleted batch {batch_num}. {updated['name']} now has {updated['current_quantity']} units.")
    else:
        print("Failed to delete.")


def _print_wall_of_shame():
    """prints expired batches from inventory at startup. syncs wall_of_shame.txt to match."""
    sync_wall_of_shame_file()
    expired = get_expired_batches_from_inventory()
    print(f"\n{BOLD}=== Wall of Shame (Expired Food) ==={RESET}")
    if not expired:
        print("  No expired batches in inventory.")
    else:
        for name, amount in expired:
            print(f"  {name} -- {amount}")
    print(f"{BOLD}===================================={RESET}\n")


def show_menu():
    """ prints the main menu options """
    print("\n--- Green-Tech Inventory Assistant ---")
    print("  1. Add new item")
    print("  2. View items (and notifications)")
    print("  3. Update quantity (restock or use)")
    print("  4. Search items")
    print("  5. Delete batch")
    print("  6. Exit")
    print()


def main():
    """ main cli loop. routes user choice to the appropriate handler """
    _print_wall_of_shame()
    while True:
        show_menu()
        choice = input("Choice (1-6): ").strip()

        if choice == "1":
            add_item()
        elif choice == "2":
            view_items()
        elif choice == "3":
            update_item()
        elif choice == "4":
            search_item()
        elif choice == "5":
            delete_batch_item()
        elif choice == "6":
            print("Goodbye!")
            sys.exit(0)
        else:
            print("Invalid choice. Enter 1-6.")


if __name__ == "__main__":
    main()
