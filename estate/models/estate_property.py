from odoo import models, fields, api
from datetime import timedelta
from odoo.exceptions import UserError, ValidationError


class EstateProperty(models.Model):
    _name = "estate.property"
    _description = "Estate Property"

    active = fields.Boolean(default=True)
    name = fields.Char(default="Property", required=True)
    state = fields.Selection(
        [
            ("new", "New"),
            ("received", "Offer Received"),
            ("accepted", "Offer Accepted"),
            ("sold", "Sold"),
            ("canceled", "Canceled"),
        ],
        required=True,
        copy=False,
        default="new",
    )
    postcode = fields.Char()

    def _default_date_availability(self):
        return fields.Date.today() + timedelta(days=90)

    date_availability = fields.Date(default=_default_date_availability, copy=False)
    description = fields.Text()
    expected_price = fields.Float(required=True)
    selling_price = fields.Float(readonly=True)
    bedrooms = fields.Integer(default=2)
    facades = fields.Integer()
    garage = fields.Boolean()
    garden = fields.Boolean()
    garden_orientation = fields.Selection(
        [("north", "North"), ("south", "South"), ("east", "East"), ("west", "West")]
    )
    property_type_id = fields.Many2one("estate.property.type", string="Property Type")
    offer_ids = fields.One2many("estate.property.offer", "property_id")
    tag_ids = fields.Many2many("estate.property.tag")
    user_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        default=lambda self: self.env.user,
    )
    buyer_id = fields.Many2one(
        "res.partner",
        string="Buyer",
        copy=False,
    )

    garden_area = fields.Integer()
    living_area = fields.Integer()
    total_area = fields.Integer(compute="_compute_total_area")

    @api.depends("living_area", "garden_area")
    def _compute_total_area(self):
        for property in self:
            property.total_area = property.living_area + property.garden_area

    best_price = fields.Float(compute="_compute_best_price")

    @api.depends("offer_ids.price")
    def _compute_best_price(self):
        for property in self:
            property.best_price = (
                max(property.offer_ids.mapped("price")) if property.offer_ids else 0
            )

    @api.onchange("garden")
    def _onchange_garden(self):
        for estate in self:
            if estate.garden:
                estate.garden_area = 10
                estate.garden_orientation = "north"
            else:
                estate.garden_area = 0
                estate.garden_orientation = False

    @api.onchange("date_availability")
    def _onchange_date_availability(self):
        if self.date_availability < fields.Date.today():
            return {
                "warning": {
                    "title": "Invalid Date",
                    "message": "The date of availability cannot be in the past",
                }
            }

    def action_sold(self):
        for property in self:
            if property.state == "canceled":
                raise UserError("This listing has already been canceled.")
            else:
                property.state = "sold"
                property.buyer_id = property.env.user.partner_id
                property.selling_price = property.best_price
                property.active = False
        return True

    def action_cancel(self):
        for property in self:
            if property.state == "sold":
                raise UserError("This listing has already been sold.")
            else:
                property.state = "canceled"
                property.active = False
        return True

    _sql_constraints = [
        (
            "check_expected_price",
            "CHECK(expected_price > 0)",
            "Expected price must be greater than 0.",
        ),
        (
            "check_selling_price",
            "CHECK(selling_price > 0)",
            "Selling price must be greater than 0.",
        ),
    ]

    @api.constrains("selling_price")
    def _check_constraints(self):
        for property in self:
            if property.selling_price < 5000:
                raise ValidationError("Selling price must be at least 5000.")
            elif property.selling_price < 0.9 * property.expected_price:
                raise ValidationError(
                    "Selling price must be at least 90% of the expected price."
                )

        return True
