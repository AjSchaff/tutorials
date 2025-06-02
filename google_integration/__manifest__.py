{
    'name': 'Google Maps Integration for Vendor Selection',
    'version': '1.0',
    'category': 'Inventory',
    'summary': 'Select vendors based on proximity to delivery address',
    'description': """
        Automatically select vendors based on their distance to delivery address:
        - Integrates with Google Maps API
        - Calculates distances between vendors and delivery locations
        - Automatically selects closest vendor for purchase orders
    """,
    'depends': [
        'base',
        'sale',
        'purchase',
        'stock',
        'contacts',
    ],
    'data': [
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
} 