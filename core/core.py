import pandas as pd
import sys
import os

# --- PATH INJECTION ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

# Absolute imports - NO DOTS
from data_processor import NodalDataProcessor
from optimizer import NodalOptimizer
from routing_engine import NodalRouter

class NodalCore:
    def __init__(self, api_key, file_path):
        """
        Coordinates the logistics flow. Now limited to a realistic 400-order morning pool.
        """
        self.processor = NodalDataProcessor(file_path)
        self.optimizer = NodalOptimizer()
        self.router = NodalRouter(api_key)
        self.all_data_cached = None
        self.DAILY_POOL_LIMIT = 400 # Senin istediğin dürüst depo limiti

    def get_top_regions(self):
        """
        SCANS only the first 400 records to reflect a realistic morning manifest.
        """
        if not self.processor.load_file():
            return None
        
        df = self.processor.standardize_columns()
        if df is None: return None
        
        # --- REALISM FILTER ---
        # No matter how big the file is, the algorithm only scans the amount registered.
        print(f"INFO: Reality Check - Limiting analysis to the first {self.DAILY_POOL_LIMIT} orders.")
        self.all_data_cached = df.head(self.DAILY_POOL_LIMIT).copy()
        
        # Extract Postcode Area (e.g., 'B' or 'NW')
        self.all_data_cached['region_code'] = self.all_data_cached['postcode'].str.extract(r'^([A-Z]{1,2})')
        
        # Group by region within the 400-order pool
        stats = self.all_data_cached.groupby('region_code').agg(
            order_count=('order_id', 'count'),
            total_courier_value=('courier_cost_gbp', 'sum')
        ).sort_values(by='total_courier_value', ascending=False).head(5)
        
        return stats

    def execute_regional_analysis(self, region_prefix, api_limit=150):
        """
        Executes analysis ONLY for the selected regional cluster within the 400-limit pool.
        """
        if self.all_data_cached is None:
            # Scanner çalışmadıysa fallback olarak 400 limitli tara
            self.get_top_regions()

        # Filter: Only look at the region prefix (e.g. 'NW') within our 400-item pool
        regional_df = self.all_data_cached[self.all_data_cached['region_code'] == region_prefix].copy()
        
        if regional_df.empty:
            print(f"WARNING: No orders found for '{region_prefix}' within the first {self.DAILY_POOL_LIMIT} orders.")
            return None, self.DAILY_POOL_LIMIT

        # Step 3: Traffic-Aware Routing (Only for the selected cluster)
        unique_pcs = regional_df['postcode'].unique()[:api_limit]
        dist_map = {}
        dur_map = {} 
        
        print(f"INFO: Fetching traffic data for {len(unique_pcs)} points in {region_prefix}...")
        
        for pc in unique_pcs:
            data = self.router.get_route_data(pc)
            if data:
                dist_map[pc] = data['distance_miles']
                dur_map[pc] = data['duration_min']
        
        regional_df['distance_miles'] = regional_df['postcode'].map(dist_map)
        regional_df['duration_min'] = regional_df['postcode'].map(dur_map)
        
        # Keep only routed orders
        df_ready = regional_df.dropna(subset=['distance_miles']).copy()

        if df_ready.empty:
            print("WARNING: No valid routing data fetched for this region.")
            return pd.DataFrame(), self.DAILY_POOL_LIMIT

        # Step 4: Regional Optimization (Human Loop Logic)
        print(f"INFO: Initiating Optimizer for {region_prefix} cluster...")
        selected_orders = self.optimizer.select_best_regional_orders(df_ready)
        
        return selected_orders, self.DAILY_POOL_LIMIT