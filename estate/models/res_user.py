from odoo import models, fields


class InheritedUser(models.Model):
    _inherit = "res.users"

    property_ids = fields.One2many(
        "estate.property",
        "user_id",
        string="Properties",
        domain=[("state", "=", "new")],
    )
