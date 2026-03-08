"""
llm logic and rule-based fallback for shelf-life prediction.
predicts typical shelf life in days for inventory items.
"""

import os
from datetime import datetime, timedelta

# fallback mapping: keywords to typical shelf life in days
SHELF_LIFE_FALLBACK = {
    "milk": 7,
    "coffee": 180,
    "paper": 3650,
    "eggs": 14,
    "bread": 5,
    "yogurt": 14,
    "cheese": 30,
    "butter": 90,
    "cleaning": 365,
    "spray": 365,
    "towels": 3650,
}

DEFAULT_SHELF_DAYS = 30


def predict_shelf_life_days(name):
    """
    predicts typical shelf life in days for an item
    tries llm first; on failure uses rule-based fallback
    returns (days, is_estimated) where is_estimated is True when fallback was used
    """
    try:
        days = _call_llm_for_shelf_life(name)
        return (days, False)
    except Exception as e:
        print(f"error calling llm for shelf life, using fallback: {e}")
        return _fallback_shelf_life(name)


def _call_llm_for_shelf_life(name):
    """
    calls the configured llm api to predict shelf life
    expects a single integer response. raises on timeout or api error
    """
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("no api key configured")
        raise ValueError("no api key configured")

    if os.getenv("OPENAI_API_KEY"):
        return _openai_predict(name)
    if os.getenv("GEMINI_API_KEY"):
        return _gemini_predict(name)
    raise ValueError("no api key configured")


def _openai_predict(name):
    """uses openai api to predict shelf life. returns integer days"""
    try:
        from openai import OpenAI

        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": f"Given the item '{name}', predict its typical shelf life in days. Return ONLY an integer.",
                }
            ],
            max_tokens=10,
        )
        text = response.choices[0].message.content.strip()
        return int("".join(c for c in text if c.isdigit()) or str(DEFAULT_SHELF_DAYS))
    except Exception as e:
        raise e


def _gemini_predict(name):
    """uses google gemini api to predict shelf life. returns integer days"""
    try:
        import google.generativeai as genai

        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(
            f"Given the item '{name}', predict its typical shelf life in days. Return ONLY an exact, positive integer."
        )
        text = response.text.strip()
        return int("".join(c for c in text if c.isdigit()) or str(DEFAULT_SHELF_DAYS))
    except Exception as e:
        raise e


def _fallback_shelf_life(name):
    """
    rule-based fallback when llm fails
    matches keywords in item name to hardcoded days; defaults to 30 if no match
    returns (days, is_estimated)
    """
    name_lower = name.lower()
    for keyword, days in SHELF_LIFE_FALLBACK.items():
        if keyword in name_lower:
            return (days, True)
    return (DEFAULT_SHELF_DAYS, True)


def compute_predicted_expiration(date_added_str, shelf_days):
    """adds shelf_days to date_added and returns expiration date as yyyy-mm-dd string."""
    dt = datetime.strptime(date_added_str, "%Y-%m-%d")
    exp = dt + timedelta(days=shelf_days)
    return exp.strftime("%Y-%m-%d")


def get_shelf_life_days(name):
    """returns shelf life in days for an item based on keyword fallback. no api call."""
    name_lc = name.lower()
    for keyword, days in SHELF_LIFE_FALLBACK.items():
        if keyword in name_lc:
            return days
    return DEFAULT_SHELF_DAYS
