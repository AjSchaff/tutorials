from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    google_maps_api_key = fields.Char(
        string='Google Maps API Key',
        config_parameter='google_integration.api_key'
    ) 