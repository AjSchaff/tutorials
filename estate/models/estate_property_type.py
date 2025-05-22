from odoo import models, fields


class PropertyType(models.Model):
    _name = "estate.property.type"
    _description = "Estate Property Type"

    name = fields.Char(string="Name", required=True)

    _sql_constraints = [
        ("check_name", "UNIQUE(name)", "Property type name must be unique."),
    ]
