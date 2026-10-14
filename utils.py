import os
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from config import PROMPTS_DIR


def calculate_final_price(base_price: int, promo: Optional[Dict[str, Any]]) -> Tuple[int, int, str]:
    """
    Возвращает (final_price, discount_value, promo_info_str).
    Минимальная цена: 0 (если скидка 100% или больше цены).
    """
    if not promo:
        return base_price, 0, ""

    percent = promo.get("discount_percent", 0)
    stars = promo.get("discount_stars", 0)

    if percent > 0:
        discount = int(round(base_price * (percent / 100.0)))
        final_price = max(0, base_price - discount)
        return final_price, discount, f"🎟 Промокод `{promo['code']}`: скидка {percent}% (-{discount} ⭐️)"
    elif stars > 0:
        discount = min(base_price, stars)
        final_price = max(0, base_price - discount)
        return final_price, discount, f"🎟 Промокод `{promo['code']}`: скидка {discount} ⭐️"

    return base_price, 0, ""


def get_prompt_file_info(filename: str) -> Dict[str, Any]:
    file_path = PROMPTS_DIR / filename
    if not file_path.exists():
        return {
            "exists": False,
            "size_kb": 0,
            "char_count": 0,
            "path": file_path
        }

    size_bytes = file_path.stat().st_size
    size_kb = round(size_bytes / 1024, 1)

    text = ""
    for enc in ["utf-8", "cp1251", "latin1"]:
        try:
            with open(file_path, "r", encoding=enc) as f:
                text = f.read()
            break
        except Exception:
            continue

    return {
        "exists": True,
        "size_kb": size_kb,
        "char_count": len(text),
        "path": file_path,
        "text": text
    }
