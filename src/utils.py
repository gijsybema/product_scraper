#utils.py

import requests

def fetch_debug(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.7,en;q=0.6",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    with requests.Session() as s:
        r = s.get(url, headers=headers, timeout=30, allow_redirects=True)
        print("STATUS:", r.status_code)
        print("FINAL URL:", r.url)
        print("LEN:", len(r.text))
        print("SERVER:", r.headers.get("server"))
        print("CACHE:", r.headers.get("x-cache"), r.headers.get("cf-cache-status"))
        print("TITLE SNIP:", r.text[:2000])

        # snelle signalen
        lowered = r.text.lower()
        print("has product cards?", "product-card" in lowered or "productkaart" in lowered)
        print("has next data?", "__next_data__" in lowered)
        block_words = ["captcha", "access denied", "blocked", "bot", "robot"]
        block_signals = ["captcha", "access denied", "blocked", "verify you are human", "too many requests"]
        hits = [w for w in block_signals if w in lowered]
        print("block signals:", hits)
        return r.text

def print_progress(current, total, identifier=None, elapsed=None, avg_time=None, est_time_left=None):
    """
    Print progress information for long-running operations.
    
    Args:
        current: Current item index (0-based)
        total: Total number of items
        identifier: Optional identifier to display (e.g., SKU, product_id)
        elapsed: Total elapsed time in seconds
        avg_time: Average time per item in seconds
        est_time_left: Estimated time remaining in seconds
    """
    percent = 100 * ((current + 1) / total)
    msg = f"[{current+1}/{total}] ({percent:.1f}%)"
    
    if identifier is not None:
        # Handle different identifier types
        if isinstance(identifier, int):
            msg += f" Product ID: {identifier}"
        elif isinstance(identifier, str):
            # If string looks numeric, treat as SKU, otherwise just display
            if identifier.isdigit():
                msg += f" SKU: {identifier}"
            else:
                msg += f" {identifier}"
        else:
            # For dict-like identifiers, show the most relevant key
            if "sku" in identifier:
                msg += f" SKU: {identifier['sku']}"
            elif "product_id" in identifier:
                msg += f" Product ID: {identifier['product_id']}"
    
    if elapsed is not None:
        msg += f" | Elapsed: {elapsed:.1f}s"
    
    if avg_time is not None and est_time_left is not None:
        eta_minutes = est_time_left / 60
        msg += f" | Avg: {avg_time:.2f}s/item, ETA: {est_time_left:.1f}s ({eta_minutes:.1f} min)"
    
    print(msg, flush=True)

if __name__ == "__main__":
    url = "https://www.coolblue.nl/hoofdtelefoons/filter"
    fetch_debug(url)