def is_outfit(text: str) -> bool:
    text = text.lower()
    return text.startswith("cid_") or text == "outfit"

def is_backpack(text: str) -> bool:
    text = text.lower()
    return text.startswith("bid_") or text in ["backpack","back bling"]