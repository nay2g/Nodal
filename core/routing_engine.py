import googlemaps
from datetime import datetime

class NodalRouter:
    def __init__(self, api_key):
        """
        Initializes the router with Google Maps API and the Kettering warehouse address.
        Includes a safety mechanism to prevent excessive API costs.
        """
        self.gmaps = googlemaps.Client(key=api_key)
        
        # --- DEPOT LOCATION ---
        # Using Postcode is more accurate for Google's pin-point calculations
        self.warehouse_postcode = "NN15 6NL" 
        
        # --- API PROTECTION & OPTIMIZATION ---
        self.route_cache = {}  
        self.daily_request_count = 0
        self.MAX_DAILY_LIMIT = 3000

    def get_route_data(self, destination_postcode):
        """
        Fetches road distance and duration. Checks cache first, then calls Google Maps API.
        Uses pessimistic traffic model for safer profit calculations.
        """
        if not destination_postcode:
            return None

        # Standardize postcode (e.g., 'b37 7gt' -> 'B37 7GT')
        pc_key = str(destination_postcode).upper().strip()

        # Step 1: Check Cache (Cost-Free)
        if pc_key in self.route_cache:
            return self.route_cache[pc_key]

        # Step 2: Safety Check
        if self.daily_request_count >= self.MAX_DAILY_LIMIT:
            print(f"CRITICAL: API limit of {self.MAX_DAILY_LIMIT} reached.")
            return None

        try:
            # Step 3: Call Google Maps API
            self.daily_request_count += 1
            
            # Using 'pessimistic' traffic model ensures our van costs are never underestimated
            result = self.gmaps.distance_matrix(
                origins=self.warehouse_postcode,
                destinations=pc_key,
                mode="driving",
                departure_time=datetime.now(),
                traffic_model="pessimistic" 
            )
            
            if result['status'] == 'OK':
                element = result['rows'][0]['elements'][0]
                if element['status'] == 'OK':
                    # Logic: Convert meters to miles (0.000621371)
                    dist_meters = element['distance']['value']
                    distance_miles = round(dist_meters * 0.000621371, 2)
                    
                    # Duration in traffic (minutes)
                    # Note: duration_in_traffic is only available with departure_time
                    duration_sec = element.get('duration_in_traffic', element['duration'])['value']
                    duration_min = round(duration_sec / 60, 2)
                    
                    route_info = {
                        'distance_miles': distance_miles,
                        'duration_min': duration_min
                    }
                    
                    # Step 4: Save to Cache
                    self.route_cache[pc_key] = route_info
                    return route_info
            
            return None

        except Exception as e:
            print(f"Google Maps API Error for {pc_key}: {e}")
            return None