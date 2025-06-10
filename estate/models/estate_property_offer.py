from odoo import fields, models, api
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare


class EstateOffer(models.Model):
    _name = "estate.property.offer"
    _description = "Offers made for real estate"
    _order = "price desc"

    price = fields.Float()
    status = fields.Selection(
        [
            ("accepted", "Accepted"),
            ("refused", "Refused"),
        ],
        copy=False,
    )
    partner_id = fields.Many2one("res.partner", required=True)
    property_id = fields.Many2one("estate.property", required=True, ondelete="cascade")
    property_type_id = fields.Many2one(
        related="property_id.property_type_id", store=True
    )

    validity = fields.Integer(default=7)
    date_deadline = fields.Date(
        compute="_compute_date_deadline", inverse="_inverse_date_deadline"
    )

    @api.constrains("price")
    def _check_price(self):
        for record in self:
            # Check minimum price (90% of expected price)
            min_price = record.property_id.expected_price * 0.9
            if float_compare(record.price, min_price, precision_digits=2) < 0:
                raise UserError(
                    "The offer price must be at least 90% of the expected price."
                )

    @api.depends("validity")
    def _compute_date_deadline(self):
        for property in self:
            property.date_deadline = fields.Date.today() + relativedelta(
                days=property.validity
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Convert property_id from int to record
            property_id = self.env["estate.property"].browse(vals.get("property_id"))
            if property_id.state == "new":
                property_id.state = "received"

            # Check if price is higher than existing offers
            existing_offers = property_id.offer_ids.filtered(
                lambda o: o.status != "refused"
            )
            if existing_offers:
                max_price = max(existing_offers.mapped("price"))
                if (
                    float_compare(vals.get("price", 0), max_price, precision_digits=2)
                    <= 0
                ):
                    raise UserError(
                        f"The offer price must be higher than the existing offer of {max_price}."
                    )
        return super().create(vals_list)

    def _inverse_date_deadline(self):
        for property in self:
            property.validity = (property.date_deadline - fields.Date.today()).days

    def action_accept(self):
        self.ensure_one()
        if "accepted" in self.property_id.offer_ids.mapped("status"):
            raise UserError("An offer has already been accepted.")
        else:
            self.status = "accepted"
            self.property_id.selling_price = self.price
            self.property_id.buyer_id = self.partner_id
            self.property_id.state = "accepted"

    def action_refuse(self):
        self.status = "refused"

    _sql_constraints = [
        ("check_price", "CHECK(price > 0)", "Price must be greater than 0."),
    ]
