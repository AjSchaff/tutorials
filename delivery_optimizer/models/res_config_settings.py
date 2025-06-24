import requests
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    SUBSCRIPTION_INACTIVE_ERROR = _(
        "Your subscription is inactive. Please renew your subscription to use route optimization."
    )

    # Your Vercel API endpoint
    VERCEL_API_BASE_URL = "https://v0-module-dashboard-git-develop-schaff-stack.vercel.app"  # Replace with your actual Vercel domain

    # Subscription fields
    subscription_id = fields.Char(
        string="Subscription ID",
        config_parameter="delivery_optimizer.subscription_id",
        help="Enter the Subscription ID from your subscription page after purchase.",
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
    fleet_vehicle_ids = fields.Many2many(
        "fleet.vehicle",
        string="Trucks",
        help="Select the trucks (fleet vehicles) to use for delivery optimization.",
    )
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

    @api.depends("fleet_vehicle_ids")
    def _compute_truck_count(self):
        for rec in self:
            rec.truck_count = len(rec.fleet_vehicle_ids)

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

    def _call_vercel_api(self, data):
        """Make a POST request to your Vercel API endpoint"""
        url = f"{self.VERCEL_API_BASE_URL}/api/check-subscription"

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Odoo-Delivery-Optimizer/1.0",
        }

        try:
            response = requests.post(url, json=data, headers=headers, timeout=15)
            response.raise_for_status()
            return response.json()

        except requests.exceptions.ConnectionError:
            _logger.error(f"Connection error when calling Vercel API: {url}")
            raise UserError(
                _(
                    "Could not connect to the subscription service. Please check your internet connection and try again."
                )
            )
        except requests.exceptions.Timeout:
            _logger.error(f"Timeout when calling Vercel API: {url}")
            raise UserError(
                _("Request to subscription service timed out. Please try again.")
            )
        except requests.exceptions.HTTPError as e:
            _logger.error(
                f"HTTP error when calling Vercel API: {url}, Status: {e.response.status_code}"
            )
            try:
                error_data = e.response.json()
                error_message = error_data.get(
                    "message", f"HTTP {e.response.status_code}"
                )
            except:
                error_message = f"HTTP {e.response.status_code}"
            raise UserError(_(f"Subscription service error: {error_message}"))
        except Exception as e:
            _logger.error(
                f"Unexpected error when calling Vercel API: {url}, Error: {str(e)}"
            )
            raise UserError(
                _(f"Unexpected error when contacting subscription service: {str(e)}")
            )

    def _check_subscription_status_vercel(self):
        """Check subscription status using your Vercel API"""
        sub_id = self.subscription_id
        if not sub_id:
            return False

        try:
            data = {
                "subscriptionId": sub_id,
                "email": self.env.user.email,
            }
            response = self._call_vercel_api(data)
            return response.get("valid", False)
        except Exception as e:
            _logger.error(
                f"Failed to check subscription status via Vercel API: {str(e)}"
            )
            return False

    def _check_subscription_status_api(self):
        """Legacy method - now calls Vercel API"""
        return self._check_subscription_status_vercel()

    def check_subscription_status(self):
        """Check subscription status and handle activation logic"""
        # Get current user's email
        current_user_email = self.env.user.email

        if not current_user_email:
            raise UserError(_("User email is required to check subscription status."))

        if not self.subscription_id:
            raise UserError(
                _(
                    "Subscription ID is required. Please enter your subscription ID first."
                )
            )

        try:
            # Call Vercel API - it handles all the activation logic
            data = {
                "subscriptionId": self.subscription_id,
                "email": current_user_email,
            }
            response = self._call_vercel_api(data)
            
            # Handle the response based on your API's response format
            if response.get('valid', False):
                message = response.get('message', 'Subscription is valid')
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
                message = response.get('message', 'Subscription is invalid')
                raise UserError(_(f"❌ {message}"))
            
        except UserError:
            raise
        except Exception as e:
            _logger.error(f"Unexpected error during subscription check: {str(e)}")
            raise UserError(_(f"Failed to check subscription: {str(e)}"))

    def get_subscription_status(self):
        # For button in UI
        active = self._check_subscription_status_vercel()
        status = "active" if active else "inactive"
        raise UserError(f"Subscription Status: {status}")
