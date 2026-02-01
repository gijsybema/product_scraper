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
