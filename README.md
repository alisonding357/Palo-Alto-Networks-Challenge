# Green-Tech Inventory Assistant

**Candidate Name: Alison Ding**  
**Scenario Chosen:** Green-Tech Inventory Assistant (CLI)  
**Estimated Time Spent: 6 hours**  

---

## Quick Start

**Prerequisites:**
- Python 3.x
- `pip install -r requirements.txt` (openai, google-generativeai, python-dotenv)
- API key: set `OPENAI_API_KEY` or `GEMINI_API_KEY` in `.env` (copy from `.env.example`)

**Run Commands:**
```bash
cd inventory_app
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your API key
python main.py
```

**Test Commands:**
```bash
cd inventory_app
pytest test_app.py -v
```

---

## AI Disclosure

- **Did you use an AI assistant (Copilot, ChatGPT, etc.)?** (Yes/No)
Yes. I used Copilot to build the CLI's frontend UI, and a bit for debugging my LLM integration, and structuring the file I/O logic for the "Wall of Shame".

- **How did you verify the suggestions?**
Because I had a clear vision for the CLI interface (an Excel-style spreadsheet layout) and used AI to generate the cosmetic formatting, I verified by running the code and seeing if the changes matched what I wanted.

- **Give one example of a suggestion you rejected or changed:**
The AI repeatedly suggested using auto-incrementing numeric IDs as the primary lookup key for the inventory data (e.g., forcing the user to type "update 1"). I rejected this and rewrote the logic to use item names as the keys because I felt it was more intuitive.

---

## Tradeoffs & Prioritization

**What did you cut to stay within the 4–6 hour limit?**
- Run-out predictions based on historical user data. Combining that with the batches logic was too complex to finish in time.

**What would you build next if you had more time?**
- Run-out predictions based on historical user data (e.g. "Your coffee supply will run out in 4 days").

**Edge case handling:**
- **Over-draft (use more than available):** If a user records usage greater than the item's quantity, the app consumes whatever is available and stops at 0. Inventory never goes negative.

**Known limitations:**
- No automatic expiration filtering – expired batches remain in FIFO until manually deleted; usage still consumes from them
- No over-draft warning – when usage exceeds available quantity, the app consumes what exists and stops at 0 but does not explicitly tell the user about the shortfall
- Single-user, single-file – no locking or concurrency
- No undo – deletions and updates are permanent
- Integer quantities only – no fractional amounts
- No backup – no versioning or recovery

---

## Project Overview

CLI inventory tracker for small businesses and sustainability-minded teams. Tracks items with per-batch expiration dates, uses AI to predict shelf life, and supports restock, usage, and batch management. A **wall of shame** logs expired food at startup to hold users accountable.

**Features:** Add item, view (with color-coded expiration), update (restock/use), search, delete batch.

**Design choices:**
- **Batches & FIFO** – Each restock is a batch with amount, dates, expiration. Usage consumes oldest first.
- **Storage** – JSON file; name as lookup key (case-insensitive).
- **AI** – LLM (OpenAI/Gemini) for shelf life with rule-based fallback on failure.
- **Wall of shame** – Logs expired units when usage consumes them or user deletes expired batches; prints at startup to raise waste awareness.

**Project structure:**
```
inventory_app/
  main.py        # CLI routing and table display
  db.py          # Load/save, batches, CRUD
  ai_service.py  # LLM shelf-life prediction and fallback
  inventory.json # Data store
  wall_of_shame.txt  # Expired food log
  test_app.py    # Pytest tests
  .env           # API keys (do not commit)
```
