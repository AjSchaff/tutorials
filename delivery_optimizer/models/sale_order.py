from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    nearest_vendor_id = fields.Many2one(
        'res.partner',
        string='Nearest Vendor',
        compute='_compute_nearest_vendor',
        store=True,
        compute_sudo=True,
    )
    
    vendor_distance = fields.Float(
        string='Distance (miles)',
        compute='_compute_vendor_distance',
        store=True,
        compute_sudo=True,
        digits=(10, 2),
        help='Distance to nearest vendor in miles'
    )

    @api.depends('partner_shipping_id')
    def _compute_nearest_vendor(self):
        for order in self:
            order.nearest_vendor_id = False
            
            if order.partner_shipping_id:
                maps_helper = self.env['delivery.optimizer.maps.helper']
                vendors = self.env['res.partner'].search([
                    ('supplier_rank', '>', 0),  # Is a vendor
                    ('active', '=', True)
                ])
                
                if vendors:
                    distance_data = maps_helper.get_distance_matrix(order.partner_shipping_id, vendors)
                    if distance_data and distance_data.get('rows'):
                        elements = distance_data['rows'][0].get('elements', [])
                        distances = []
                        for i, element in enumerate(elements):
                            if element.get('status') == 'OK':
                                meters = element.get('distance', {}).get('value', 999999)
                                miles = meters * 0.000621371
                                distances.append((vendors[i], meters, miles))
                        
                        if distances:
                            nearest = min(distances, key=lambda x: x[1])
                            order.nearest_vendor_id = nearest[0]

    @api.depends('partner_shipping_id', 'nearest_vendor_id')
    def _compute_vendor_distance(self):
        for order in self:
            order.vendor_distance = 0.0
            
            if order.partner_shipping_id and order.nearest_vendor_id:
                maps_helper = self.env['delivery.optimizer.maps.helper']
                distance_data = maps_helper.get_distance_matrix(order.partner_shipping_id, order.nearest_vendor_id)
                if distance_data and distance_data.get('rows'):
                    elements = distance_data['rows'][0].get('elements', [])
                    if elements and elements[0].get('status') == 'OK':
                        meters = elements[0].get('distance', {}).get('value', 0)
                        order.vendor_distance = meters * 0.000621371 