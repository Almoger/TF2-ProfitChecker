"""
TF2 SCM & backpack.tf market scanner (using snapshot API)
"""
import os
import csv
import time
import requests
import random
import json

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


# load all tf2 item names from bp.tf
def get_all_item_names():
    url = "https://backpack.tf/api/IGetPrices/v4"
    data = http_get_json(url, params={"key": BACKPACK_TF_API_KEY, "appid": APPID, "raw": 1})
    return list(data["response"]["items"].keys())

if __name__ == "__main__":
    if not BACKPACK_TF_API_KEY:
        print("Please set BACKPACK_TF_API_KEY")
        exit(1)

    names = get_all_item_names()
    random.shuffle(names)
    
    for base_name in names:
        for quality in QUALITIES:
            sku = f"{QUALITY_PREFIX[quality]}{base_name}"
            print(sku)
            bp_metal, best_buyer, buyers = get_bp_snapshot_buy(sku)
            if not bp_metal or not buyers:
                continue
            scm_usd = get_scm_price_usd(sku)
            if not scm_usd:
                continue
            key_bp = bp_metal / KEY_REF
            key_scm = scm_usd / KEY_ILS
            profit = key_bp - key_scm
            val = {
                "item": sku,
                "SteamMarket_PriceILS": round(scm_usd, 2),
                "SteamMarket_PriceInKeys": round(key_scm, 2),
                "BP_PriceInKeys": round(key_bp, 2),
                "buyers": buyers,
                "BestBuyer": f"https://backpack.tf/classifieds?steamid={best_buyer}&quality={QUALITY_ID[quality]}&item={base_name}",
                "profit": round(profit, 2)
            }
            
            if(profit > -0.1 and scm_usd < 16.3 and key_scm >= 1.0):
                print(val)
                with open("data.json", "a", encoding="utf-8") as f:
                    json.dump(val, f, ensure_ascii=False)
                    f.write("\n")
