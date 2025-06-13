import requests
import logging
from odoo import models, fields
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    subscription_id = fields.Char(
        string="Subscription ID",
        config_parameter="estate.property.subscription_id",
        help="Enter the Subscription ID from your external billing account.",
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

    def get_subscription_status(self):
        _logger.info("Self in get_subscription_status: %s", self)
        base_url = (
            "https://58f4dc8f-57cb-4bb7-b758-a8afa5af776e.mock.pstmn.io/subscriptions/"
        )
        sub_id = self.subscription_id
        if not sub_id:
            raise UserError("No Subscription ID configured.")

        try:
            url = f"{base_url}{sub_id}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                status = data.get("status", "unknown")
                raise UserError(f"Subscription Status: {status}")
            else:
                raise UserError(f"Error: {response.status_code}")
        except UserError:
            raise
        except Exception as e:
            raise UserError(f"Exception: {str(e)}")

    def check_subscription_status(self):
        _logger.info("Self in check_subscription_status: %s", self)
        return self.get_subscription_status()
