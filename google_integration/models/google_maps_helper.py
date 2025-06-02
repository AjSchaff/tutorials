import requests
import logging
from odoo import models, tools

_logger = logging.getLogger(__name__)

class GoogleMapsHelper(models.AbstractModel):
    _name = 'google.maps.helper'
    _description = 'Google Maps Integration Helper'

    def _get_api_key(self):
        """Get API key from secure mydb storage"""
        try:
            self.env.cr.execute("""
                SELECT api_key 
                FROM mydb.google_api_key 
                WHERE id = 1
            """)
            result = self.env.cr.fetchone()
            if result and result[0]:
                return result[0]
            _logger.error("No API key found in mydb")
        except Exception as e:
            _logger.error("Error getting API key from mydb: %s", str(e))
        return False

    def get_distance_matrix(self, origin, destinations):
        """Calculate distances between origin and multiple destinations"""
        api_key = self._get_api_key()
        if not api_key:
            _logger.error("Google Maps API key not configured")
            return False

        base_url = "https://maps.googleapis.com/maps/api/distancematrix/json"
        
        # Format destinations for the API
        dest_str = "|".join([f"{d.street}, {d.city}, {d.state_id.name}, {d.zip}, {d.country_id.name}" 
                            for d in destinations if d.street])
        origin_str = f"{origin.street}, {origin.city}, {origin.state_id.name}, {origin.zip}, {origin.country_id.name}"

        params = {
            'origins': origin_str,
            'destinations': dest_str,
            'key': api_key
        }

        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            result = response.json()

            if result.get('status') == 'OK':
                return result
            else:
                _logger.error("Google Maps API error: %s", result.get('status'))
                return False

        except Exception as e:
            _logger.error("Error calling Google Maps API: %s", str(e))
            return False 