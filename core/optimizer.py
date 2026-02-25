import pandas as pd
import csv
from datetime import datetime
import os

class NodalOptimizer:
    def __init__(self, van_capacity_m3=12.0, van_capacity_kg=1500.0):
        # --- PHYSICAL CONSTRAINTS ---
        self.raw_max_m3 = van_capacity_m3
        self.van_capacity_kg = van_capacity_kg
        self.UTILIZATION_RATIO = 0.80 
        self.van_capacity_m3 = self.raw_max_m3 * self.UTILIZATION_RATIO
        
        # --- FIXED OPERATIONAL COSTS ---
        self.DRIVER_DAILY_RATE = 140.00
        self.VEHICLE_INSURANCE_DAILY = 15.00
        self.MAINTENANCE_BUFFER = 10.00
        self.LONDON_SURCHARGE = 15.00
        self.SAFETY_MARGIN = 1.10  
        
        # --- DYNAMIC FUEL SETTINGS ---
        self.current_diesel_price = 1.45
        self.VAN_MPG = 30.0
        self.calculate_fuel_per_mile()

    def calculate_fuel_per_mile(self):
        self.FUEL_COST_PER_MILE = (self.current_diesel_price * 4.546) / self.VAN_MPG

    def is_london(self, postcode):
        if pd.isna(postcode): return False
        pc = str(postcode).upper().strip()
        return pc.startswith(('EC', 'WC', 'E1', 'N1', 'NW1', 'SE1', 'SW1', 'W1'))

    def calculate_human_route_miles(self, dist_to_region, num_stops):
        """
        Calculates a realistic route: (Depot to Region * 2) + (Local Drop Density).
        In UK cities, average distance between close drops is 1.2 miles.
        """
        stem_miles = dist_to_region * 2 # Go to region and return to Kettering
        drop_miles = num_stops * 1.2    # Distance covered during deliveries
        return round(stem_miles + drop_miles, 2)

    def calculate_van_cost(self, total_miles, has_london_stop):
        fixed = self.DRIVER_DAILY_RATE + self.VEHICLE_INSURANCE_DAILY + self.MAINTENANCE_BUFFER
        fuel = total_miles * self.FUEL_COST_PER_MILE
        total = fixed + fuel
        if has_london_stop: total += self.LONDON_SURCHARGE
        return total * self.SAFETY_MARGIN

    def select_best_regional_orders(self, df):
        """
        NEW: Selects orders for a specific region and applies Human Routing logic.
        """
        if df is None or df.empty: return pd.DataFrame()
        
        # Priority: Save the most expensive courier costs first
        df_sorted = df.sort_values(by='courier_cost_gbp', ascending=False)

        selected_orders = []
        curr_vol, curr_kg = 0, 0
        # The region's distance is anchored to the furthest postcode in the group
        dist_to_region = df['distance_miles'].max() 

        for index, row in df_sorted.iterrows():
            if (curr_vol + row['volume_m3'] <= self.van_capacity_m3) and \
               (curr_kg + row['weight_kg'] <= self.van_capacity_kg):
                
                selected_orders.append(row)
                curr_vol += row['volume_m3']
                curr_kg += row['weight_kg']

        result_df = pd.DataFrame(selected_orders)

        if not result_df.empty:
            # Applying the 'Human' mileage logic instead of summing random trips
            total_route_miles = self.calculate_human_route_miles(dist_to_region, len(result_df))
            
            savings = result_df['courier_cost_gbp'].sum()
            has_london = any(self.is_london(pc) for pc in result_df['postcode'])
            cost = self.calculate_van_cost(total_route_miles, has_london)
            
            # Store the final calculated miles for reporting
            result_df['final_route_miles'] = total_route_miles
            
            if cost > savings:
                print(f"DEBUG: Regional Van cost (£{cost:.2f}) > Savings (£{savings:.2f}).")
                return pd.DataFrame() 

        return result_df

    def log_daily_results(self, total_orders_count, selected_df, total_miles, status="USED", note=""):
        log_file = "data/nodal_history.csv"
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        courier_saving = round(selected_df['courier_cost_gbp'].sum(), 2) if not selected_df.empty else 0
        
        if status == "USED" and not selected_df.empty:
            has_lon = any(self.is_london(pc) for pc in selected_df['postcode'])
            nodal_cost = round(self.calculate_van_cost(total_miles, has_lon), 2)
        else:
            nodal_cost = 0

        profit = round(courier_saving - nodal_cost, 2)
        
        file_exists = os.path.isfile(log_file)
        with open(log_file, mode='a', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Date", "Total_Orders", "Selected_Orders", "Nodal_Cost", "Courier_Saving", "Net_Profit", "Status", "Notes"])
            
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d"),
                total_orders_count,
                len(selected_df),
                nodal_cost,
                courier_saving,
                profit,
                status,
                note
            ])
        print(f"INFO: Day logged as {status} with £{profit} profit.")