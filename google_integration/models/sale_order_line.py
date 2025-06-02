from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _get_closest_vendor(self):
        """Find the closest vendor for the product based on delivery address"""
        self.ensure_one()
        
        if not self.product_id or not self.order_id.partner_shipping_id:
            return False

        # Get all potential vendors for this product
        suppliers = self.env['product.supplierinfo'].search([
            ('product_tmpl_id', '=', self.product_id.product_tmpl_id.id),
        ])

        if not suppliers:
            return False

        # Get unique vendors (some might be listed multiple times with different conditions)
        vendors = suppliers.mapped('partner_id')
        
        # Get distance matrix from Google Maps
        maps_helper = self.env['google.maps.helper']
        delivery_address = self.order_id.partner_shipping_id
        
        distance_data = maps_helper.get_distance_matrix(delivery_address, vendors)
        
        if not distance_data:
            return False

        # Process distance matrix results
        distances = []
        for i, element in enumerate(distance_data.get('rows', [{}])[0].get('elements', [])):
            if element.get('status') == 'OK':
                distances.append((vendors[i], element.get('distance', {}).get('value', 999999)))

        # Sort by distance and get the closest vendor
        if distances:
            closest_vendor = min(distances, key=lambda x: x[1])[0]
            _logger.info("Selected closest vendor %s for delivery to %s", 
                        closest_vendor.name, delivery_address.name)
            return closest_vendor

        return False

    def _prepare_procurement_values(self, group_id=False):
        """Override to set the closest vendor"""
        values = super()._prepare_procurement_values(group_id=group_id)
        
        # Get the closest vendor
        vendor = self._get_closest_vendor()
        if vendor:
            _logger.info("Setting closest vendor %s for procurement", vendor.name)
            values['supplier_id'] = vendor
            values['partner_id'] = vendor.id
        
        return values 