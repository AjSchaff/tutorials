from odoo import _, models, fields, api


class PropertyType(models.Model):
    _name = "estate.property.type"
    _inherit = "estate.mixin"
    _description = "Estate Property Type"
    _order = "sequence, name"

    sequence = fields.Integer(default=1)
    property_ids = fields.One2many("estate.property", "property_type_id")
    offer_ids = fields.One2many("estate.property.offer", "property_type_id")
    offer_count = fields.Integer(compute="_compute_offer_count")
    property_count = fields.Integer(compute="_compute_property_count")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self.env["estate.property.tag"].create(
                {
                    "name": vals.get("name"),
                }
            )
        return super().create(vals_list)

    def unlink(self):
        self.property_ids.state = "cancel"
        return super().unlink()

    _sql_constraints = [
        ("check_name", "UNIQUE(name)", "Property type name must be unique."),
    ]

    @api.depends("offer_ids")
    def _compute_offer_count(self):
        for rec in self:
            rec.offer_count = len(rec.offer_ids)

    @api.depends("property_ids")
    def _compute_property_count(self):
        for rec in self:
            rec.property_count = len(rec.property_ids)

    def action_open_property_ids(self):
        return {
            "name": _("Related Properties"),
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "res_model": "estate.property",
            "target": "current",
            "domain": [("property_type_id", "=", self.id)],
            "context": {
                "default_property_type_id": self.id,
            },
        }

    def action_open_offer_ids(self):
        return {
            "name": _("Related Offers"),
            "type": "ir.actions.act_window",
            "view_mode": "list,form",
            "res_model": "estate.property.offer",
            "target": "current",
            "domain": [("property_type_id", "=", self.id)],
            "context": {
                "default_property_type_id": self.id,
            },
        }
