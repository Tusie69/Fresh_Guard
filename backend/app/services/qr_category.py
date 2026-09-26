"""Fixed QR labels that identify FreshGuard food categories."""


QR_CATEGORY_MAPPING = {
    "FG-MEAT": "MEAT",
    "FG-DAIRY": "DAIRY",
    "FG-VEGETABLE": "VEGETABLE",
    "FG-FRUIT": "FRUIT",
    "FG-COOKED": "COOKED_FOOD",
}


def category_for_qr_code(qr_code):
    """Return the mapped category, allowing surrounding whitespace only."""
    if not isinstance(qr_code, str):
        return None
    return QR_CATEGORY_MAPPING.get(qr_code.strip())


def is_supported_category(category):
    return category in QR_CATEGORY_MAPPING.values()
