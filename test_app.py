"""
tests for the green-tech inventory assistant.
covers happy path (add item, calculate expiration, save) and fallback (fake api key).
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ai_service import compute_predicted_expiration, predict_shelf_life_days
from db import add_item, load_inventory, record_usage, INVENTORY_PATH


def test_add_item_calculates_expiration_and_saves():
    """
    happy path: adding an item successfully calculates an expiration date
    and saves it to the json file.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_file = Path(tmpdir) / "inventory.json"
        with patch("db.INVENTORY_PATH", inventory_file):
            date_added = "2025-03-06"
            shelf_days = 14
            predicted_expiration = compute_predicted_expiration(date_added, shelf_days)

            item = add_item(
                name="test coffee",
                quantity=2,
                date_added=date_added,
                predicted_expiration=predicted_expiration,
            )

            assert item["name"] == "test coffee"
            assert item["current_quantity"] == 2
            assert item["date_added"] == date_added
            assert item["predicted_expiration"] == "2025-03-20"
            assert len(item["batches"]) == 1
            assert item["batches"][0]["amount"] == 2

            with open(inventory_file) as f:
                saved = json.load(f)
            assert len(saved) == 1
            assert saved[0]["predicted_expiration"] == "2025-03-20"


def test_fallback_assigns_7_day_shelf_life_to_milk():
    """
    edge case: with a fake api key, the rule-based fallback correctly
    assigns a 7-day shelf life to "milk".
    """
    with patch.dict(os.environ, {"OPENAI_API_KEY": "fake", "GEMINI_API_KEY": ""}):
        days, is_estimated = predict_shelf_life_days("milk")
        assert days == 7
        assert is_estimated is True


def test_record_usage_over_draft_stops_at_zero():
    """
    edge case: using more than available consumes what exists and stops at 0.
    inventory never goes negative.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        inventory_file = Path(tmpdir) / "inventory.json"
        with patch("db.INVENTORY_PATH", inventory_file), patch("db.EXPIRED_LOG_PATH", Path(tmpdir) / "wall_of_shame.txt"):
            add_item(
                name="test eggs",
                quantity=5,
                date_added="2025-03-01",
                predicted_expiration="2025-03-15",
            )
            updated = record_usage("test eggs", 10)
            assert updated is not None
            assert updated["current_quantity"] == 0
            assert len(updated["batches"]) == 0
