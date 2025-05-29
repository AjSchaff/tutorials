from odoo import models, fields


class PropertyType(models.Model):
    _name = "estate.property.type"
    _description = "Estate Property Type"
    _order = "sequence, name"

    sequence = fields.Integer(default=1)
    name = fields.Char(required=True)
    property_ids = fields.One2many("estate.property", "property_type_id")

    _sql_constraints = [
        ("check_name", "UNIQUE(name)", "Property type name must be unique."),
    ]
