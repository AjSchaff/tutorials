import requests
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    SUBSCRIPTION_INACTIVE_ERROR = _('Your subscription is inactive. Please renew your subscription to use route optimization.')

    # Subscription fields
    subscription_id = fields.Char(
        string="Subscription ID",
        config_parameter="estate.property.subscription_id",
        help="Enter the Subscription ID from your external billing account.",
    )

    # Fleet/Truck management fields
    fleet_vehicle_ids = fields.Many2many(
        'fleet.vehicle',
        string='Trucks',
        help='Select the trucks (fleet vehicles) to use for delivery optimization.'
    )
    truck_count = fields.Integer(
        string='Number of Trucks',
        compute='_compute_truck_count',
        store=False
    )
    subscription_tier = fields.Selection(
        [
            ('basic', 'Basic (1 Truck)'),
            ('tier2', 'Tier 2 (2-5 Trucks)'),
            ('tier3', 'Tier 3 (5-10 Trucks)'),
            ('tier4', 'Tier 4 (10+ Trucks)'),
        ],
        string='Subscription Tier',
        compute='_compute_subscription_tier',
        store=False
    )

    auto_optimize_routes = fields.Boolean(
        string="Auto-optimize Delivery Routes",
        config_parameter="nko_google.auto_optimize_routes",
        help="Automatically optimize delivery routes at scheduled intervals",
    )

    optimize_route_interval = fields.Selection(
        [
            ("hourly", "Hourly"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
        ],
        string="Optimization Interval",
        config_parameter="nko_google.optimize_route_interval",
        default="daily",
        help="Frequency of automatic route optimization",
    )

    @api.depends('fleet_vehicle_ids')
    def _compute_truck_count(self):
        for rec in self:
            rec.truck_count = len(rec.fleet_vehicle_ids)

    @api.depends('truck_count')
    def _compute_subscription_tier(self):
        for rec in self:
            count = rec.truck_count
            if count <= 1:
                rec.subscription_tier = 'basic'
            elif 2 <= count <= 5:
                rec.subscription_tier = 'tier2'
            elif 6 <= count <= 10:
                rec.subscription_tier = 'tier3'
            else:
                rec.subscription_tier = 'tier4'

    def _check_subscription_status_api(self):
        base_url = "https://58f4dc8f-57cb-4bb7-b758-a8afa5af776e.mock.pstmn.io/subscriptions/"
        sub_id = self.subscription_id
        if not sub_id:
            return False
        try:
            url = f"{base_url}{sub_id}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                return status == "active"
            else:
                return False
        except Exception as e:
            _logger.error(f"Subscription check failed: {str(e)}")
            return False

    def check_subscription_status(self):
        return self._check_subscription_status_api()

    def get_subscription_status(self):
        # For button in UI
        active = self._check_subscription_status_api()
        status = "active" if active else "inactive"
        raise UserError(f"Subscription Status: {status}")
