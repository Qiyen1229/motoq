"""快速輸入：公升/度數、單價、總額 三者填兩個，自動算出第三個。"""


def resolve_amounts(
    quantity: float | None, unit_price: float | None, total: int | None
) -> tuple[float, float, int]:
    if sum(v is not None for v in (quantity, unit_price, total)) < 2:
        raise ValueError("數量、單價、總額至少需填兩項")
    if quantity is None:
        if not unit_price:
            raise ValueError("單價必須大於 0")
        quantity = total / unit_price  # type: ignore[operator]
    elif unit_price is None:
        if not quantity:
            raise ValueError("數量必須大於 0")
        unit_price = total / quantity  # type: ignore[operator]
    elif total is None:
        total = round(quantity * unit_price)
    if quantity <= 0:
        raise ValueError("數量必須大於 0")
    return round(quantity, 3), round(unit_price, 2), int(round(total))  # type: ignore[arg-type]
