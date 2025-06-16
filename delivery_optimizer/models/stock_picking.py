import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
from itertools import permutations
from .res_config_settings import ResConfigSettings

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

    def _validate_address(self, partner):
        """Validate if a partner has a complete address"""
        if not partner:
            return False
        required_fields = ["street", "city", "zip"]
        missing_fields = [field for field in required_fields if not partner[field]]
        if missing_fields:
            _logger.warning(
                f"Partner {partner.name} is missing fields: {', '.join(missing_fields)}"
            )
            return False

        # Log the complete address for debugging
        _logger.info(
            f"Valid address for {partner.name}: {partner.street}, {partner.city}, {partner.zip}"
        )
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
                    _logger.warning(
                        f"Distance calculation failed between points {current_point} and {next_point}"
                    )
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
                _logger.warning(
                    f"Return distance calculation failed from point {current_point}"
                )
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
                        "optimized_sequence": "Incoming Shipment",
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
                        "optimized_sequence": "Update Delivery Date",
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

        # Log all valid addresses
        for d in valid_deliveries:
            addr = d.partner_id
            _logger.info(
                f"Valid address for {addr.name}: {addr.street}, {addr.street2}, {addr.city}, "
                f"{addr.state_id.name if addr.state_id else ''}, {addr.zip}, "
                f"{addr.country_id.code if addr.country_id else ''}"
            )

        addresses = [warehouse.partner_id] + [d.partner_id for d in valid_deliveries]
        if len(addresses) < 2:
            return True

        distance_matrix = self._build_distance_matrix(addresses)
        best_route = self._find_best_route(valid_deliveries, distance_matrix)

        if not best_route:
            raise UserError(_("Could not find a valid route."))

        total_distance = self._calculate_route_distance(best_route, distance_matrix)
        self._assign_stop_numbers(
            best_route, valid_deliveries, addresses, distance_matrix, total_distance
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
        _logger.info(f"Searching for warehouse with company_id: {self.env.company.id}")
        _logger.info(f"Company name: {self.env.company.name}")

        # Let's also log all warehouses in the system to see what's available
        all_warehouses = self.env["stock.warehouse"].search([])
        _logger.info(
            f"All warehouses in system: {[(w.name, w.company_id.name) for w in all_warehouses]}"
        )

        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )

        # Add logging to show what warehouse was found
        _logger.info(f"Found warehouse: {warehouse.name if warehouse else 'None'}")
        if warehouse and warehouse.partner_id:
            _logger.info(f"Warehouse partner: {warehouse.partner_id.name}")
            _logger.info(
                f"Warehouse address: {warehouse.partner_id.street}, {warehouse.partner_id.city}, {warehouse.partner_id.zip}"
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
        addr_map = {}
        for d in deliveries:
            key = self._get_address_key(d.partner_id)
            _logger.info(
                f"Delivery {d.name} address key: {key} (Partner: {d.partner_id.name})"
            )
            addr_map.setdefault(key, []).append(d)

        used_keys, stop = set(), 1
        today = fields.Date.context_today(self)
        for idx in route:
            partner = addresses[idx]
            key = self._get_address_key(partner)
            _logger.info(f"Assigning stop {stop} to key: {key}")
            if key in used_keys:
                continue
            used_keys.add(key)
            for i, d in enumerate(addr_map.get(key, []), 1):
                # Check if scheduled_date is in the past
                if d.scheduled_date and fields.Date.to_date(d.scheduled_date) < today:
                    d.write(
                        {
                            "optimized_sequence": "Update Delivery Date",
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
                        "optimized_sequence": (
                            stop if len(addr_map[key]) == 1 else float(f"{stop}.{i}")
                        ),
                        "distance_from_warehouse": dist,
                        "total_route_distance": total_dist,
                    }
                )
            stop += 1

    def action_optimize_route(self):
        """Manual trigger for route optimization, processes all eligible deliveries for today."""
        company = self.env.company
        today = fields.Date.context_today(self)
        today_str = fields.Date.to_string(today)

        # Check subscription status before proceeding
        config = self.env["res.config.settings"].create({})
        if not config.check_subscription_status():
            raise UserError(ResConfigSettings.SUBSCRIPTION_INACTIVE_ERROR)

        pickings = self.env["stock.picking"].search(
            [
                ("picking_type_id.code", "=", "outgoing"),
                ("picking_type_id", "=", 2),
                ("state", "in", ("assigned", "confirmed")),
                ("company_id", "=", company.id),
            ]
        )
        if not pickings:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("No Eligible Deliveries"),
                    "message": _(
                        "No outgoing deliveries in assigned or confirmed state were found for company %s."
                        % company.name
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }
        try:
            self._optimize_delivery_route(pickings)
            return {
                "type": "ir.actions.client",
                "tag": "reload",
            }
        except Exception as e:
            _logger.error(f"Route optimization failed: {str(e)}")
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Error"),
                    "message": str(e),
                    "type": "danger",
                    "sticky": True,
                },
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
            [("company_id", "=", self.env.company.id)], limit=1
        )
        if (
            not warehouse
            or not warehouse.partner_id
            or not (
                warehouse.partner_id.street
                and warehouse.partner_id.city
                and warehouse.partner_id.zip
            )
        ):
            raise UserError(_("No valid warehouse address found."))
        # Filter valid deliveries
        valid_deliveries = []
        for p in pickings:
            addr = p.partner_id
            if addr and addr.street and addr.city and addr.zip:
                valid_deliveries.append(p)
        if not valid_deliveries:
            raise UserError(_("No valid delivery addresses found."))
        # Build addresses list for optimizer
        addresses = [warehouse.partner_id] + [d.partner_id for d in valid_deliveries]
        distance_matrix = self._build_distance_matrix(addresses)
        best_route = self._find_best_route(valid_deliveries, distance_matrix)
        if not best_route:
            raise UserError(_("Could not find a valid route."))
        # Build the ordered address list: warehouse -> optimized deliveries (no duplicates) -> warehouse
        ordered_addresses = [warehouse.partner_id]
        seen = set()
        for idx in best_route:
            partner = addresses[idx]
            key = (
                (partner.street or "").strip().lower(),
                (partner.street2 or "").strip().lower(),
                (partner.city or "").strip().lower(),
                (partner.state_id.name if partner.state_id else "").strip().lower(),
                (partner.zip or "").strip(),
                (partner.country_id.code if partner.country_id else "").strip().upper(),
            )
            if key not in seen:
                seen.add(key)
                ordered_addresses.append(partner)
        ordered_addresses.append(warehouse.partner_id)  # Return to warehouse
        # Format for Google Maps
        formatted_addresses = [
            f"{a.street}, {a.city}, {a.zip}" for a in ordered_addresses
        ]
        base_url = "https://www.google.com/maps/dir/"
        route_url = base_url + "/".join(
            addr.replace(" ", "+") for addr in formatted_addresses
        )
        return {
            "type": "ir.actions.act_url",
            "url": route_url,
            "target": "new",
        }
