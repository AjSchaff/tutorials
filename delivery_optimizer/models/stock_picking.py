import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta, date
from itertools import permutations
from collections import defaultdict

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    optimized_sequence = fields.Char(
        string="Stop #",
        help="Stop number after route optimization or a status message",
        copy=False,
    )

    distance_from_warehouse = fields.Float(
        string="Distance from WH (mi)",
        help="Distance from warehouse to delivery address",
        copy=False,
        readonly=True,
        digits=(16, 2),  # 2 decimal places for miles
    )

    total_route_distance = fields.Float(
        string="Total Distance (mi)",
        help="Total distance of the optimized route including return to warehouse",
        copy=False,
        readonly=True,
        digits=(16, 2),
    )

    def _format_address(self, partner):
        """Format address for Google Maps API."""
        return f"{partner.street}, {partner.city}, {partner.zip}"

    def _call_vercel_optimize_route(self, addresses):
        """Call Vercel API to get optimized route and distance matrix."""
        url = "https://preview.vikuno.com/api/optimize-route"  # <-- update to your actual endpoint
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Odoo-Delivery-Optimizer/1.0",
        }
        data = {"addresses": [self._format_address(addr) for addr in addresses]}
        import requests

        try:
            response = requests.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
            result = response.json()
            if "error" in result:
                raise UserError(
                    _("Failed to get optimized route: %s") % result["error"]
                )
            return result["route"], result["distance_matrix"]
        except Exception as e:
            _logger.error(f"Error calling Vercel optimize route: {e}")
            raise UserError(_("Failed to get optimized route from server."))

    def _validate_subscription(self):
        """Validate subscription status and revalidate if needed"""
        current_user_email = self.env.user.email
        if not current_user_email:
            raise UserError(_("User email is required to validate subscription."))
        subscription_id = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("delivery_optimizer.subscription_id")
        )
        if not subscription_id:
            raise UserError(
                _(
                    "Subscription ID is required. Please enter your subscription ID in Settings → Delivery Route Optimizer → Subscription Settings."
                )
            )
        try:
            data = {
                "subscriptionId": subscription_id,
                "email": current_user_email,
            }

            url = "https://preview.vikuno.com/api/check-subscription"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Odoo-Delivery-Optimizer/1.0",
            }
            import requests

            response = requests.post(url, json=data, headers=headers, timeout=15)
            response.raise_for_status()
            result = response.json()
            if not result.get("valid", False):
                message = result.get("message", "Subscription is invalid")
                raise UserError(_(f"❌ {message}"))
            return True
        except UserError:
            raise
        except Exception as e:
            _logger.error(f"Failed to validate subscription: {str(e)}")
            raise UserError(
                _(
                    "Failed to validate subscription. Please try again or contact support."
                )
            )

    def _validate_address(self, partner):
        """Validate if a partner has a complete address"""
        if not partner:
            return False
        required_fields = ["street", "city", "zip"]
        missing_fields = [field for field in required_fields if not partner[field]]
        if missing_fields:
            return False

        return True

    def _meters_to_miles(self, meters):
        """Convert meters to miles"""
        return meters * 0.000621371  # Standard conversion factor

    def _calculate_route_distance(self, route, distance_matrix):
        """Calculate total distance for a given route, skipping duplicate delivery points, and returning to warehouse."""

        if not distance_matrix or not distance_matrix.get("rows"):
            raise UserError(_("Invalid distance matrix received from Google Maps API."))

        total_distance = 0
        current_point = 0  # Start at warehouse
        visited = set()  # To keep track of delivery points we've already visited

        for next_point in route:
            if next_point in visited:
                continue  # Skip if already visited
            visited.add(next_point)

            try:
                distance_element = distance_matrix["rows"][current_point]["elements"][
                    next_point
                ]
                if distance_element.get("status") != "OK":
                    raise UserError(
                        _(
                            "Could not calculate distance between some locations. Please verify addresses."
                        )
                    )
                total_distance += distance_element["distance"]["value"]
                current_point = next_point
            except (KeyError, IndexError) as e:
                _logger.error(f"Error processing distance matrix: {str(e)}")
                raise UserError(_("Invalid response format from Google Maps API."))

        # Add distance from last delivery back to warehouse (point 0)
        try:
            return_element = distance_matrix["rows"][current_point]["elements"][0]
            if return_element.get("status") != "OK":
                raise UserError(
                    _(
                        "Could not calculate return distance to warehouse. Please verify addresses."
                    )
                )
            total_distance += return_element["distance"]["value"]
        except (KeyError, IndexError) as e:
            _logger.error(f"Error processing return distance: {str(e)}")
            raise UserError(
                _("Invalid response format for return distance calculation.")
            )

        return self._meters_to_miles(total_distance)  # Convert meters to miles

    def _optimize_delivery_route(self, deliveries):
        if not deliveries:
            return False

        warehouse = self._get_validated_warehouse()
        today = fields.Date.context_today(self)

        valid_deliveries = []
        for delivery in deliveries:
            # Exclude incoming pickings
            if delivery.picking_type_id.code == "incoming":
                delivery.write(
                    {
                        "optimized_sequence": "",
                        "distance_from_warehouse": 0,
                        "total_route_distance": 0,
                    }
                )
                continue
            # Exclude past dates
            if (
                delivery.scheduled_date
                and fields.Date.to_date(delivery.scheduled_date) < today
            ):
                delivery.write(
                    {
                        "optimized_sequence": "",
                        "distance_from_warehouse": 0,
                        "total_route_distance": 0,
                    }
                )
                continue
            # Exclude future dates (do not mark, just skip)
            if (
                delivery.scheduled_date
                and fields.Date.to_date(delivery.scheduled_date) > today
            ):
                delivery.write(
                    {
                        "optimized_sequence": "",
                        "distance_from_warehouse": 0,
                        "total_route_distance": 0,
                    }
                )
                continue
            valid_deliveries.append(delivery)

        # Skip if no valid deliveries after filtering
        if not valid_deliveries:
            return True

        # Filter for valid addresses
        valid_deliveries = self._filter_valid_deliveries(valid_deliveries)
        if not valid_deliveries:
            return True

        addresses = [warehouse.partner_id] + [d.partner_id for d in valid_deliveries]
        if len(addresses) < 2:
            return True

        route, distance_matrix = self._call_vercel_optimize_route(addresses)

        total_distance = self._calculate_route_distance(route, distance_matrix)
        self._assign_stop_numbers(
            route, valid_deliveries, addresses, distance_matrix, total_distance
        )

        return True

    def _group_deliveries_by_date(self, deliveries):
        grouped = {}
        for d in deliveries:
            date_str = fields.Date.to_string(d.scheduled_date)
            grouped.setdefault(date_str, []).append(d)
        return grouped

    def _get_validated_warehouse(self):
        # Log the company_id we're searching with
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )

        if not warehouse or not warehouse.partner_id:
            raise UserError(_("Please configure warehouse address first."))
        if not self._validate_address(warehouse.partner_id):
            raise UserError(_("Warehouse address is incomplete."))
        return warehouse

    def _filter_valid_deliveries(self, deliveries):
        return [
            d
            for d in deliveries
            if d.partner_id and self._validate_address(d.partner_id)
        ]

    def _build_distance_matrix(self, addresses):
        matrix = {"rows": []}
        helper = self.env["google.maps.helper"]
        for origin in addresses:
            res = helper.get_distance_matrix(origin, addresses)
            if not res or res.get("status") != "OK" or not res.get("rows"):
                raise UserError(
                    _("Failed to get distance matrix from Google Maps API.")
                )
            matrix["rows"].append(res["rows"][0])
        return matrix

    def _find_best_route(self, deliveries, matrix):
        count = len(deliveries)
        if count <= 8:
            return self._brute_force_route(count, matrix)
        return self._nearest_neighbor_route(count, matrix)

    def _brute_force_route(self, count, matrix):
        best, min_dist = None, float("inf")
        for route in permutations(range(1, count + 1)):
            try:
                dist = self._calculate_route_distance(route, matrix)
                if dist < min_dist:
                    best, min_dist = route, dist
            except Exception:
                continue
        return best

    def _nearest_neighbor_route(self, count, matrix):
        route, unvisited, current = [], list(range(1, count + 1)), 0
        while unvisited:
            try:
                next_pt = min(
                    unvisited,
                    key=lambda x: matrix["rows"][current]["elements"][x]["distance"][
                        "value"
                    ],
                )
                route.append(next_pt)
                current = next_pt
                unvisited.remove(next_pt)
            except Exception:
                raise UserError(_("Error calculating route."))
        return route

    def _calculate_route_distance(self, route, matrix):
        dist = 0
        current = 0
        for point in route:
            dist += matrix["rows"][current]["elements"][point]["distance"]["value"]
            current = point
        dist += matrix["rows"][current]["elements"][0]["distance"][
            "value"
        ]  # back to warehouse
        return self._meters_to_miles(dist)

    def _assign_stop_numbers(self, route, deliveries, addresses, matrix, total_dist):
        from collections import defaultdict

        today = fields.Date.context_today(self)
        addr_map = defaultdict(list)
        for d in deliveries:
            if d.scheduled_date and fields.Date.to_date(d.scheduled_date) == today:
                key = self._get_address_key(d.partner_id)
                addr_map[key].append(d)
            else:
                d.write(
                    {
                        "optimized_sequence": "",
                        "distance_from_warehouse": 0,
                        "total_route_distance": 0,
                    }
                )

        used_keys = set()
        stop = 1
        for idx in route:
            if idx < 1 or idx >= len(addresses):
                continue  # skip warehouse (index 0) and out-of-range
            partner = addresses[idx]
            key = self._get_address_key(partner)
            if key in used_keys:
                continue
            used_keys.add(key)
            deliveries_at_address = addr_map.get(key, [])
            dist = 0
            if matrix and "rows" in matrix and len(matrix["rows"]) > 0:
                try:
                    dist = self._meters_to_miles(
                        matrix["rows"][0]["elements"][idx]["distance"]["value"]
                    )
                except Exception:
                    dist = 0
            for i, d in enumerate(deliveries_at_address, 1):
                seq = stop if len(deliveries_at_address) == 1 else float(f"{stop}.{i}")
                d.write(
                    {
                        "optimized_sequence": seq,
                        "distance_from_warehouse": dist,
                        "total_route_distance": (
                            total_dist if total_dist is not None else 0
                        ),
                    }
                )
            stop += 1

    def action_optimize_route(self):
        self._validate_subscription()

        company = self.env.company
        today = fields.Date.context_today(self)

        all_pickings = self.env["stock.picking"].search(
            [
                ("picking_type_id.code", "=", "outgoing"),
                ("picking_type_id", "=", 2),
                ("state", "in", ("assigned", "confirmed")),
                ("company_id", "=", company.id),
            ]
        )

        todays_deliveries = [
            p
            for p in all_pickings
            if p.scheduled_date
            and fields.Date.to_date(p.scheduled_date) == today
            and p.partner_id
            and p.partner_id.street
            and p.partner_id.city
            and p.partner_id.zip
        ]
        not_today_deliveries = [p for p in all_pickings if p not in todays_deliveries]

        # Reset all non-today deliveries
        for d in not_today_deliveries:
            d.write(
                {
                    "optimized_sequence": "",
                    "distance_from_warehouse": 0,
                    "total_route_distance": 0,
                }
            )

        if not todays_deliveries:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("No Eligible Deliveries"),
                    "message": _(
                        "No outgoing deliveries in assigned or confirmed state were found for today."
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }

        warehouse = self._get_validated_warehouse()
        addresses = [warehouse.partner_id] + [d.partner_id for d in todays_deliveries]
        route, distance_matrix = self._call_vercel_optimize_route(addresses)
        self._assign_stop_numbers(
            route, todays_deliveries, addresses, distance_matrix, None
        )

        # Calculate total route distance (warehouse -> unique stops in route order -> warehouse)
        unique_route = []
        seen_keys = set()
        for idx in route:
            if idx < 1 or idx >= len(addresses):
                continue
            partner = addresses[idx]
            key = self._get_address_key(partner)
            if key not in seen_keys:
                unique_route.append(idx)
                seen_keys.add(key)
        path = [0] + unique_route + [0]  # warehouse -> unique stops -> warehouse
        total_distance = 0
        for i in range(len(path) - 1):
            from_idx = path[i]
            to_idx = path[i + 1]
            total_distance += distance_matrix["rows"][from_idx]["elements"][to_idx][
                "distance"
            ]["value"]
        total_distance = self._meters_to_miles(total_distance)

        for i in range(len(path) - 1):
            from_idx = path[i]
            to_idx = path[i + 1]
            dist = distance_matrix["rows"][from_idx]["elements"][to_idx]["distance"][
                "value"
            ]
        for d in todays_deliveries:
            d.write({"total_route_distance": total_distance})

        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }

    def _get_address_key(self, partner):
        """Return a normalized unique key for a delivery address."""
        return (
            (partner.street or "").strip().lower(),
            (partner.street2 or "").strip().lower(),
            (partner.city or "").strip().lower(),
            (partner.state_id.name if partner.state_id else "").strip().lower(),
            (partner.zip or "").strip(),
            (partner.country_id.code if partner.country_id else "").strip().upper(),
        )

    def action_open_google_maps_route(self):
        """Open Google Maps with optimized route - requires active subscription"""
        self._validate_subscription()  # Ensure subscription is valid

        company = self.env.company
        today = fields.Date.context_today(self)
        today_str = fields.Date.to_string(today)

        pickings = self.env["stock.picking"].search(
            [
                ("picking_type_id.code", "=", "outgoing"),
                ("state", "in", ("assigned", "confirmed")),
                ("scheduled_date", ">=", today_str + " 00:00:00"),
                ("scheduled_date", "<=", today_str + " 23:59:59"),
            ]
        )
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", company.id)], limit=1
        )
        if not warehouse or not warehouse.partner_id:
            raise UserError(_("No valid warehouse address found."))

        valid_deliveries = [
            p
            for p in pickings
            if p.partner_id
            and p.partner_id.street
            and p.partner_id.city
            and p.partner_id.zip
        ]
        if not valid_deliveries:
            raise UserError(_("No valid delivery addresses found."))

        addresses = [warehouse.partner_id] + [d.partner_id for d in valid_deliveries]
        # Only add warehouse at the end if it's not already the last stop
        if addresses[-1] != warehouse.partner_id:
            addresses.append(warehouse.partner_id)
        route, _ = self._call_vercel_optimize_route(addresses)

        # Build the ordered address list: warehouse -> optimized deliveries (no duplicates) -> warehouse
        ordered_addresses = [warehouse.partner_id]
        seen = set()
        for idx in route:
            partner = addresses[idx]
            key = (partner.street, partner.city, partner.zip)
            if key not in seen:
                seen.add(key)
                ordered_addresses.append(partner)
        # Only add warehouse at the end if it's not already the last stop
        if ordered_addresses[-1] != warehouse.partner_id:
            ordered_addresses.append(warehouse.partner_id)

        formatted_addresses = [self._format_address(a) for a in ordered_addresses]
        base_url = "https://www.google.com/maps/dir/"
        route_url = base_url + "/".join(
            addr.replace(" ", "+") for addr in formatted_addresses
        )
        return {
            "type": "ir.actions.act_url",
            "url": route_url,
            "target": "new",
        }
