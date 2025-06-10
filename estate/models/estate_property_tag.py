from odoo import fields, models


class EstatePropertyTag(models.Model):
    _name = "estate.property.tag"
    _description = "Property Tag"
    _inherit = "estate.mixin"

    _sql_constraints = [
        ("unique_tag_name", "UNIQUE(name)", "Tag name must be unique."),
    ]
    _order = "name desc"

    color = fields.Integer()
