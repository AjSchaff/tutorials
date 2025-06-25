import requests
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Base URL for your Vercel API
    VERCEL_API_BASE_URL = "https://preview.vikuno.com"

    # API endpoints (these will be appended to the base URL)
    SUBSCRIPTION_CHECK_ENDPOINT = "/api/check-subscription"
    GOOGLE_OPTIMIZE_ENDPOINT = "/api/google/optimize-route"

    # Subscription fields
    subscription_id = fields.Char(
        string="Subscription ID",
        help="Enter your subscription ID from the purchase confirmation",
        config_parameter="delivery_optimizer.subscription_id",
    )

    # Activation tracking fields
    activated = fields.Boolean(
        string="Activated",
        config_parameter="delivery_optimizer.activated",
        default=False,
        help="Whether this subscription has been activated",
    )

    activated_by = fields.Char(
        string="Activated By",
        config_parameter="delivery_optimizer.activated_by",
        help="Email address of the user who activated this subscription",
    )

    # Fleet/Truck management fields
    # fleet_vehicle_ids = fields.Many2many(
    #     "fleet.vehicle",
    #     string="Trucks",
    #     help="Select the trucks (fleet vehicles) to use for delivery optimization.",
    # )

    truck_count = fields.Integer(
        string="Number of Trucks", compute="_compute_truck_count", store=False
    )
    subscription_tier = fields.Selection(
        [
            ("basic", "Basic (1 Truck)"),
            ("tier2", "Tier 2 (2-5 Trucks)"),
            ("tier3", "Tier 3 (5-10 Trucks)"),
            ("tier4", "Tier 4 (10+ Trucks)"),
        ],
        string="Subscription Tier",
        compute="_compute_subscription_tier",
        store=False,
    )

    auto_optimize_routes = fields.Boolean(
        string="Auto-optimize Delivery Routes",
        config_parameter="delivery_optimizer.auto_optimize_routes",
        help="Automatically optimize delivery routes at scheduled intervals",
    )

    optimize_route_interval = fields.Selection(
        [
            ("hourly", "Hourly"),
            ("daily", "Daily"),
            ("weekly", "Weekly"),
        ],
        string="Optimization Interval",
        config_parameter="delivery_optimizer.optimize_route_interval",
        default="daily",
        help="Frequency of automatic route optimization",
    )

    # @api.depends("fleet_vehicle_ids")
    # def _compute_truck_count(self):
    #     for rec in self:
    #         rec.truck_count = len(rec.fleet_vehicle_ids)

    @api.depends("truck_count")
    def _compute_subscription_tier(self):
        for rec in self:
            count = rec.truck_count
            if count <= 1:
                rec.subscription_tier = "basic"
            elif 2 <= count <= 5:
                rec.subscription_tier = "tier2"
            elif 6 <= count <= 10:
                rec.subscription_tier = "tier3"
            else:
                rec.subscription_tier = "tier4"

    def _call_vercel_api(self, data, endpoint=None):
        """Make API call to Vercel with proper error handling"""
        if endpoint is None:
            endpoint = self.SUBSCRIPTION_CHECK_ENDPOINT

        url = f"{self.VERCEL_API_BASE_URL}{endpoint}"

        try:
            response = requests.post(
                url, json=data, headers={"Content-Type": "application/json"}, timeout=30
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_message = (
                f"HTTP {response.status_code}" if hasattr(e, "response") else str(e)
            )
            _logger.error(
                f"HTTP error when calling Vercel API: {url}, Status: {error_message}"
            )
            raise UserError(_(f"Subscription Code not found."))

    def check_subscription_status(self):
        """Check subscription status using your Vercel API"""
        if not self.subscription_id:
            raise UserError(_("Please enter a subscription ID first."))

        user_email = self.env.user.email
        if not user_email:
            raise UserError(
                _("User email is required. Please set your email in your user profile.")
            )

        try:
            data = {"subscriptionId": self.subscription_id, "email": user_email}
            response = self._call_vercel_api(data, "/api/check-subscription")
            if response.get("valid"):
                message = response.get("message", "Subscription validated successfully")
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Subscription"),
                        "message": f"✅ {message}",
                        "type": "success",
                        "sticky": False,
                    },
                }
            else:
                error_msg = response.get("message", "Subscription validation failed")
                raise UserError(_(error_msg))
        except Exception as e:
            _logger.error(f"Failed to check subscription via Vercel API: {str(e)}")
            raise UserError(_("Subscription service error: %s") % str(e))

    def get_subscription_status(self):
        # For button in UI
        active = self._check_subscription_status_vercel()
        status = "active" if active else "inactive"
        raise UserError(f"Subscription Status: {status}")

    def _assign_stop_numbers(self, route, deliveries, addresses, matrix, total_dist):
        addr_map = {}
        for d in deliveries:
            key = self._get_address_key(d.partner_id)
            addr_map.setdefault(key, []).append(d)

        used_keys = set()
        stop = 1
        today = fields.Date.context_today(self)
        for idx in route:
            if idx >= len(addresses):
                _logger.warning(
                    f"Route index {idx} out of range for addresses (len={len(addresses)})"
                )
                continue  # Skip invalid indices

            partner = addresses[idx]
            key = self._get_address_key(partner)
            if key in used_keys:
                continue
            used_keys.add(key)
            for d in addr_map.get(key, []):
                if d.scheduled_date and fields.Date.to_date(d.scheduled_date) != today:
                    d.write(
                        {
                            "optimized_sequence": "",
                            "distance_from_warehouse": 0,
                            "total_route_distance": 0,
                        }
                    )
                    continue
                dist = self._meters_to_miles(
                    matrix["rows"][0]["elements"][idx]["distance"]["value"]
                )
                d.write(
                    {
                        "optimized_sequence": stop,
                        "distance_from_warehouse": dist,
                        "total_route_distance": total_dist,
                    }
                )
            stop += 1
