{
    "name": "Delivery Route Optimizer",
    "version": "1.0",
    "category": "Inventory",
    "summary": "Optimize delivery routes using Google Maps",
    "description": """
        Optimize delivery routes using Google Maps API:
        - Integrates with Google Maps API for route optimization
        - Calculates optimal delivery sequence
        - Updates delivery order sequence automatically
        - Manual optimization trigger available
    """,
    "author": "NKO",
    "website": "https://www.nko.com",
    "depends": [
        "base",
        "stock",
        "google_integration",
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
