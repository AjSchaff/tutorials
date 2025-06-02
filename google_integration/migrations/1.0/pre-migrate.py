from odoo import SUPERUSER_ID, api

def migrate(cr, version):
    if not version:
        return
    
    # Add vendor_distance column if it doesn't exist
    cr.execute("""
        ALTER TABLE sale_order 
        ADD COLUMN IF NOT EXISTS vendor_distance numeric;
    """) 