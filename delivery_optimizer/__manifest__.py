{
    "name": "Delivery Route Optimizer",
    "version": "18.0.0.0.0",
    "category": "Inventory/Delivery",
    "summary": "Optimize delivery routes using Google Maps",
    "description": """
        Optimize delivery routes using Google Maps API:
        - Integrates with Google Maps API for route optimization (via secure proxy)
        - Calculates optimal delivery sequence
        - Updates delivery order sequence automatically
        - Manual optimization trigger available
    """,
    "author": "https://github.com/AjSchaff",
    "depends": [
        "base",
        "sale",
        "purchase",
        "stock",
        "contacts",
    ],
    "data": [
        "views/stock_picking_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "images": ["static/description/icon.png"],
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "LGPL-3",
}
