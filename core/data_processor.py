import pandas as pd
import os

class NodalDataProcessor:
    def __init__(self, file_path):
        self.file_path = file_path
        self.raw_data = None
        self.standardized_data = None

    def load_file(self):
        """Loads CSV or Excel files with robust encoding support for UK manifests."""
        try:
            ext = os.path.splitext(self.file_path)[1].lower()
            if ext == '.csv':
                # Handling specialized characters in UK addresses/names
                self.raw_data = pd.read_csv(self.file_path, encoding='utf-8', on_bad_lines='skip')
            else:
                self.raw_data = pd.read_excel(self.file_path, engine='openpyxl')
            
            # Standardizing column names (lowercase & stripped)
            self.raw_data.columns = [str(c).lower().strip() for c in self.raw_data.columns]
            print(f"INFO: Successfully loaded {os.path.basename(self.file_path)}")
            return True
        except Exception as e:
            print(f"CRITICAL ERROR: Loading failed: {e}")
            return False

    def standardize_columns(self):
        """Maps diverse carrier headers and handles multi-item quantity logic."""
        if self.raw_data is None: return None

        # Enhanced Alias Map covering DX, EVRi and common UK variations
        aliases = {
            'order_id': ['consignment number', 'barcode', 'tracking number', 'manifest number'],
            'courier_cost_gbp': ['consignment price', 'total rate', 'charge', 'price', 'invoice rate'],
            'postcode': ['delivery post code', 'destination postcode', 'postcode', 'delivery postcode'],
            'weight_kg': ['consignment weight', 'weight', 'parcel weight', 'actual weight'],
            'quantity': ['number of items', 'pieces', 'qty', 'count', 'item count'] 
        }

        final_mapping = {}
        for std, potentials in aliases.items():
            for alias in potentials:
                if alias in self.raw_data.columns:
                    final_mapping[alias] = std
                    break

        self.standardized_data = self.raw_data.rename(columns=final_mapping)

        # 1. QUANTITY LOGIC: Crucial for multi-item rows (e.g., DX 'Number of Items')
        if 'quantity' in self.standardized_data.columns:
            self.standardized_data['quantity'] = pd.to_numeric(self.standardized_data['quantity'], errors='coerce').fillna(1)
        else:
            self.standardized_data['quantity'] = 1

        # 2. WEIGHT CONVERSION & MULTIPLIER: Handle grams to kg and scale by quantity
        if 'weight_kg' in self.standardized_data.columns:
            self.standardized_data['weight_kg'] = pd.to_numeric(self.standardized_data['weight_kg'], errors='coerce').fillna(0)
            # Treat values > 500 as grams (typical for DX files)
            if self.standardized_data['weight_kg'].max() > 500:
                self.standardized_data['weight_kg'] /= 1000
            
            # IMPORTANT: Total weight for the row = Unit Weight * Quantity
            self.standardized_data['weight_kg'] = self.standardized_data['weight_kg'] * self.standardized_data['quantity']

        # 3. VOLUME INJECTION & MULTIPLIER: Scaling default volume by quantity
        if 'volume_m3' not in self.standardized_data.columns:
            # Check for EVRi volume first
            if 'volume' in self.raw_data.columns:
                self.standardized_data['volume_m3'] = pd.to_numeric(self.raw_data['volume'], errors='coerce').fillna(0.1)
            else:
                self.standardized_data['volume_m3'] = 0.1 
            
            # Scaling volume: Each item in the row takes space
            self.standardized_data['volume_m3'] = self.standardized_data['volume_m3'] * self.standardized_data['quantity']

        # 4. PRICE DATA: Courier costs in manifests are usually row-totals
        if 'courier_cost_gbp' in self.standardized_data.columns:
            self.standardized_data['courier_cost_gbp'] = pd.to_numeric(self.standardized_data['courier_cost_gbp'], errors='coerce').fillna(0)
        
        # Ensure only standardized columns are returned
        required = ['order_id', 'courier_cost_gbp', 'postcode', 'weight_kg', 'volume_m3', 'quantity']
        present_cols = [c for c in required if c in self.standardized_data.columns]
        
        return self.standardized_data[present_cols].copy()