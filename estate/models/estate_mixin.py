from odoo import models, fields


class EstateMixin(models.Model):
    _name = "estate.mixin"
    _description = "Estate Mixin"

    name = fields.Char(required=True)
