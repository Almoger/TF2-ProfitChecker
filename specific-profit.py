import os
import csv
import time
import requests
import random
import json
from urllib.parse import quote

APPID = 440
BACKPACK_TF_API_KEY = "" #FILL WITH YOUR API KEY
COUNTRY = "US"
CURRENCY = 35 # ILS
REQUEST_DELAY = 0.5
KEY_REF = 54.0
KEY_ILS = 7.24
QUALITIES = ["Unique", "Genuine", "Vintage", "Strange", "Haunted", "Collector's"]
QUALITY_PREFIX = {"Unique": "", "Genuine": "Genuine ", "Vintage": "Vintage ", "Strange": "Strange ", "Haunted": "Haunted ", "Collector's": "Collector's "}
QUALITY_ID = {"Genuine": 1, "Vintage": 3, "Unique": 6, "Strange": 11, "Haunted": 13, "Collector's": 14}

SCM_PRICE_OVERVIEW = (
    "https://steamcommunity.com/market/priceoverview/"
    "?country={country}&currency={currency}&appid={appid}&market_hash_name={name}"
)

def quality_id_to_name(qid: int):
    """Convert quality ID to quality name, based on QUALITY_ID."""
    for name, _id in QUALITY_ID.items():
        if _id == qid:
            return name
    return None

def http_get_json(url, params=None, retries=10, backoff=10):
    attempt = 0
    while attempt < retries:
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return r.json()

        except requests.exceptions.HTTPError as e:
            retry_after = r.headers.get("Retry-After") if 'r' in locals() else None
            wait_time = int(retry_after) if retry_after else backoff * (attempt + 1)
            print(f"[Attempt {attempt+1}] HTTP error {r.status_code} - waiting {wait_time} seconds before retry...")

        except requests.exceptions.RequestException as e:
            wait_time = backoff * (attempt + 1)
            print(f"[Attempt {attempt+1}] Request failed: {e} - waiting {wait_time} seconds before retry...")

        time.sleep(wait_time)
        attempt += 1
    
    return None


def parse_money(s):
    import re
    if not s:
        return None
    m = re.findall(r"[0-9]+[.,]?[0-9]*", s)
    if not m:
        return None
    return float(m[0].replace(",", "."))

def get_scm_price_usd(name, retries=10, backoff=10):
    attempt = 0
    data = http_get_json(SCM_PRICE_OVERVIEW.format(country=COUNTRY, currency=CURRENCY, appid=APPID, name=name))
    return parse_money(data.get("lowest_price") or data.get("median_price"))

def _to_int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None

def get_bp_snapshot_buy(sku, retries=10, backoff=6):
    url = "https://backpack.tf/api/classifieds/listings/snapshot"
    attempt = 0
    data = http_get_json(url, params={"appid": APPID, "sku": sku, "token": "kUEx0pEYxqHCguYBjGLxmbWuCk2UklDKta4tgq7ukKg=" })
    
    if "listings" not in data:
        return None, None, None
        
    buy_list = data["listings"]
    best_metal = None
    best_buyer = None
    buyers = 0
    for lst in buy_list:
        if str(lst["intent"]) != "buy":
            continue
            
        cur = lst["currencies"]
        if not cur:
            continue
            
        item = lst["item"]
        attrs = item.get("attributes") or []
        has_blocked = False
        for attr in attrs:
            # using var named di to check if attr is a dict or int
            di = None
            if isinstance(attr, dict):
                di = _to_int(attr.get("defindex"))
            elif isinstance(attr, (int, str)):
                di = _to_int(attr)
            if di in {1004, 1005, 1006, 1007, 1008, 1009, 142, 380, 382, 384}:
                has_blocked = True
                break
        if has_blocked:
            continue
            
        keys = float(cur.get("keys", 0) or 0)
        metal = float(cur.get("metal", 0) or 0)
        metal_val = metal + keys * KEY_REF
        buyers += 1
        if best_metal is None or metal_val > best_metal:
            best_metal = metal_val
            best_buyer = lst["steamid"]
    return best_metal, best_buyer, buyers


def scan_single_item(base_name: str, quality_id: int):
    """Scan a single item by name and quality ID, return val dict or None on failure."""
    quality_name = quality_id_to_name(quality_id)
    if not quality_name:
        print(f"Error: quality_id {quality_id} not found in QUALITY_ID.")
        return None

    sku = f"{QUALITY_PREFIX[quality_name]}{base_name}"

    # Backpack.tf buy prices
    bp_metal, best_buyer, buyers = get_bp_snapshot_buy(sku)
    if not bp_metal or not buyers:
        print("No suitable buyers found on backpack.tf for this item/quality.")
        return None

    # Steam Community Market prices in ILS
    scm_ils = get_scm_price_usd(sku)
    if not scm_ils:
        print("No price found on Steam Market for this item/quality.")
        return None

    key_bp = bp_metal / KEY_REF
    key_scm = scm_ils / KEY_ILS
    profit = key_bp - key_scm

    val = {
        "item": sku,
        "SteamMarket_PriceILS": round(scm_ils, 2),
        "SteamMarket_PriceInKeys": round(key_scm, 2),
        "BP_PriceInKeys": round(key_bp, 2),
        "buyers": buyers,
        "BestBuyer": f"https://backpack.tf/classifieds?steamid={best_buyer}&quality={quality_id}&item={quote(base_name, safe='')}",
        "profit": round(profit, 2)
    }
    return val

if __name__ == "__main__":
    while True:
        try:
            base_name = input("Enter item name (e.g., Team Captain): ").strip()
            quality_id_str = input(f"Enter QUALITY ID (options: {sorted(QUALITY_ID.values())}): ").strip()
            quality_id = int(quality_id_str)
        except Exception as e:
            print(f"Input error: {e}")
            raise SystemExit(1)

        if not base_name:
            print("Error: Item name cannot be empty.")
            raise SystemExit(1)

        result = scan_single_item(base_name, quality_id)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))


