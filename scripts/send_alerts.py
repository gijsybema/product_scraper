"""
Send Telegram alerts for price drops.

Rule (MVP):
- drop_pct >= 10
- new_price >= 150
- only unsent rows (price_drops.sent_at IS NULL)
- only today's drops (new_scraped_at = CURRENT_DATE)
- only products that are available (price_history.availability = TRUE)

Usage:
    python scripts/send_alerts.py
Env vars required:
    TELEGRAM_BOT_TOKEN
    TELEGRAM_CHAT_ID
"""

import os
import sys
from pathlib import Path
from decimal import Decimal
import requests
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env.local")

from src.db import get_connection

DROP_PCT_THRESHOLD = Decimal("5")   # 5 = 5%
MIN_NEW_PRICE = Decimal("150")
#DROP_PCT_THRESHOLD = Decimal("0")   
#MIN_NEW_PRICE = Decimal("0")

def fetch_due_drops(conn):
    sql = """
    SELECT
      pd.id AS drop_id,
      pd.product_id,
      p.name,
      p.product_url,
      pd.old_price,
      pd.new_price,
      pd.price_diff,
      pd.drop_percentage,
      pd.new_scraped_at
    FROM price_drops pd
    JOIN products p ON p.id = pd.product_id
    JOIN price_history ph 
    ON ph.product_id = pd.product_id 
    AND ph.scraped_at = pd.new_scraped_at
    WHERE p.active = true
      AND pd.sent_at IS NULL
      AND pd.new_scraped_at = CURRENT_DATE
      AND pd.new_price >= %s
      AND pd.drop_percentage >= %s
      AND pd.drop_percentage IS NOT NULL
      AND ph.availability = TRUE
    ORDER BY pd.drop_percentage DESC
    LIMIT 1
    ;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (MIN_NEW_PRICE, DROP_PCT_THRESHOLD))
        rows = cur.fetchall()

    # map tuple rows -> dict (no need for cursor.description gymnastics for MVP)
    results = []
    for r in rows:
        results.append({
            "drop_id": r[0],
            "product_id": r[1],
            "name": r[2],
            "product_url": r[3],
            "old_price": r[4],
            "new_price": r[5],
            "price_diff": r[6], 
            "drop_pct": r[7],
            "new_scraped_at": r[8],
        })
    return results


def mark_sent(conn, drop_id: int):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE price_drops SET sent_at = NOW() WHERE id = %s",
            (drop_id,)
        )
    conn.commit()


def format_message(d):
    # Make it readable + clickable. Telegram auto-links URLs.
    old_price = f"€{d['old_price']:.0f}" if d["old_price"] is not None else "—"
    new_price = f"€{d['new_price']:.0f}" if d["new_price"] is not None else "—"
    drop_pct = f"{Decimal(d['drop_pct']):.0f}%"
    price_diff = f"€{d['price_diff']:.0f}" if d["price_diff"] is not None else "—"

    return (
        f"🔻 Price drop ({drop_pct})\n\n"
        f"{d['name']}\n"
        f"{old_price} → {new_price}\n\n"
        f"Besparing: {price_diff}\n\n"
        f"{d['product_url']}"
    )


def send_telegram_message(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        #"parse_mode": "Markdown", #Tijdelijk uitgeschakeld om ongeldige markdown te voorkomen
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, json=payload, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendMessage failed: {data}")
    return data


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    def mask(s):
        return "MISSING" if not s else s[:6] + "..." + s[-4:]

    print("[ENV] token =", mask(token))
    print("[ENV] chat_id =", chat_id or "MISSING")

    if not token or not chat_id:
        raise SystemExit("Missing env vars: TELEGRAM_BOT_TOKEN and/or TELEGRAM_CHAT_ID")

    conn = get_connection()
    try:
        drops = fetch_due_drops(conn)
        if not drops:
            print("[ALERTS] no due drops")
            return

        print(f"[ALERTS] due_drops={len(drops)}")

        for d in drops:
            msg = format_message(d)
            try:
                send_telegram_message(token, chat_id, msg)
                #mark_sent(conn, d["drop_id"]) -- Tijdelijk uitgeschakeld voor testen
                print(f"[ALERTS] sent drop_id={d['drop_id']} product_id={d['product_id']}")
            except Exception as e:
                # IMPORTANT: do NOT mark as sent on failure
                print(f"[ALERTS] FAILED drop_id={d['drop_id']} error={e}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()