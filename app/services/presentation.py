"""Small look-and-feel helpers for templates (emoji and colours).

The database stores no emoji or colours, so cards without a photo get a friendly
picture chosen from the category name.
"""

CATEGORY_STYLES = {
    "Fruits & Vegetables": ("🥬", "#e6f6ea"),
    "Dairy & Sweets": ("🥛", "#e7f1fd"),
    "Bakery": ("🍞", "#fff1d6"),
    "Groceries & Staples": ("🌾", "#f6ecd9"),
    "Snacks": ("🍿", "#ffe8e0"),
    "Household": ("🧴", "#eae6fb"),
    "Stationery": ("✏️", "#fde7f1"),
}
DEFAULT_STYLE = ("🛍️", "#f1f3f5")

SHOP_TINTS = ["#e6f6ea", "#e7f1fd", "#fff1d6", "#f6ecd9", "#ffe8e0", "#eae6fb", "#fde7f1"]


def category_style(category):
    """Return (emoji, background colour) for a Category (or None)."""
    if category is None:
        return DEFAULT_STYLE
    return CATEGORY_STYLES.get(category.name, DEFAULT_STYLE)


def shop_tint(shop):
    """A stable background colour for a shop card, based on its id."""
    return SHOP_TINTS[shop.id % len(SHOP_TINTS)]
