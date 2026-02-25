import os
import sys
import pandas as pd
from datetime import datetime

# --- PATH CONFIGURATION ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

try:
    from core import NodalCore
except ImportError:
    from core.core import NodalCore

def run_nodal_app():
    # --- CONFIGURATION ---
    API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "YOUR_API_KEY_HERE")
    BASE_DIR = os.path.dirname(CURRENT_DIR)
    DATA_DIR = os.path.join(BASE_DIR, "data")
    
    if not os.path.exists(DATA_DIR):
        return print(f"CRITICAL ERROR: Data directory '{DATA_DIR}' not found.")

    files = [f for f in os.listdir(DATA_DIR) if not f.startswith('.') and f.endswith(('.csv', '.xlsx'))]
    if not files: 
        return print("CRITICAL ERROR: No manifest files found in /data folder.")
    
    manifest_path = os.path.join(DATA_DIR, files[0])
    nodal_brain = NodalCore(api_key=API_KEY, file_path=manifest_path)

    # --- 1. REGIONAL SCANNER (400 Order Pool) ---
    print("\n" + "█"*55)
    print("         NODAL REGIONAL CLUSTER ANALYZER")
    print(f"      (Analyzing Morning Pool: {nodal_brain.DAILY_POOL_LIMIT} Orders)")
    print("█"*55)
    
    # Core içindeki head(400) kuralını çalıştırır
    top_regions = nodal_brain.get_top_regions()
    if top_regions is not None:
        print("\nTop delivery clusters found in today's manifest:")
        print(top_regions)
    else:
        return print("CRITICAL: Could not analyze regions.")

    selected_region = input("\nEnter Postcode Prefix to target (e.g. NW, B, DY): ").upper().strip()

    # --- 2. DYNAMIC FUEL PRICE ---
    print("\n" + "-"*35)
    try:
        fuel_input = input("Enter today's Diesel price per litre (£) [Default 1.45]: ")
        if fuel_input.strip():
            nodal_brain.optimizer.current_diesel_price = float(fuel_input)
        nodal_brain.optimizer.calculate_fuel_per_mile()
    except ValueError:
        print("WARNING: Invalid input. Using defaults.")
    print("-"*35)

    # --- 3. EXECUTION PIPELINE (Regional Mode) ---
    print(f"INFO: Analyzing {selected_region} region from the morning pool...")
    best_orders, pool_size = nodal_brain.execute_regional_analysis(selected_region, api_limit=150)
    
    if best_orders is None or best_orders.empty:
        print(f"\n❌ NO PROFITABLE ROUTE: In this pool of {pool_size}, {selected_region} is not viable.")
        return 

    # --- 4. HUMAN & TRAFFIC REPORTING ---
    est_courier_saving = best_orders['courier_cost_gbp'].sum()
    # Optimizer'dan gelen Stem + Loop (Gidiş-Dönüş + Dağıtım) mili
    est_van_miles = best_orders['final_route_miles'].iloc[0] 
    
    # Şoförün gerçek mesaisi: Yol Sürüşü (25mph ort) + Durak başı 3 dk (0.05h)
    est_drive_time_hours = (est_van_miles / 25) + (len(best_orders) * 0.05)
    
    has_london = any(nodal_brain.optimizer.is_london(pc) for pc in best_orders['postcode'])
    total_van_cost = nodal_brain.optimizer.calculate_van_cost(est_van_miles, has_london)
    net_profit = est_courier_saving - total_van_cost

    print("\n" + "█"*55)
    print(f"         NODAL REPORT: {selected_region} OPERATIONAL PLAN")
    print("█"*55)
    print(f"Pool Size:          {pool_size} (Today's arrivals)")
    print(f"Orders in Van:      {len(best_orders)} units")
    print(f"Human Route Est:    {est_van_miles:.2f} miles (Stem + Loop)")
    print(f"Est. Shift Time:    {est_drive_time_hours:.1f} hours (Inc. Drops)")
    
    print("-" * 55)
    print(f"COURIER SAVED:      £{est_courier_saving:.2f}")
    print(f"VAN OPERATING COST: -£{total_van_cost:.2f}")
    print("-" * 55)
    
    if net_profit > 0:
        print(f"🟢 NET DAILY PROFIT:     £{net_profit:.2f}")
    else:
        print(f"🔴 NET LOSS:            £{net_profit:.2f}")
    
    if est_drive_time_hours > 9:
        print("\n⚠️  WARNING: Route exceeds legal driving limits for one driver!")
    print("█"*55)

    # --- 5. USER DECISION & DISPATCH LIST ---
    print("\nACTION REQUIRED:")
    print("[1] CONFIRM & EXPORT: Create Dispatch List for driver")
    print("[2] REJECT: Do not use van for this region")
    print("[3] EXIT")
    
    choice = input("Enter selection: ")

    if choice == '1':
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        dispatch_filename = f"dispatch_{selected_region}_{timestamp}.csv"
        dispatch_path = os.path.join(DATA_DIR, dispatch_filename)
        
        # Sürücü için gereken net liste
        cols_to_export = ['order_id', 'postcode', 'weight_kg', 'volume_m3']
        if 'quantity' in best_orders.columns:
            cols_to_export.append('quantity')
            
        best_orders[cols_to_export].to_csv(dispatch_path, index=False)
        
        print(f"\n✅ SUCCESS: Dispatch list created: {dispatch_filename}")
        print(f"👉 Path: {DATA_DIR}")
        print("-" * 55)
        
        note = input("Add optional note (e.g., Driver Name): ")
        nodal_brain.optimizer.log_daily_results(
            total_orders_count=pool_size, 
            selected_df=best_orders, 
            total_miles=est_van_miles, 
            status="USED", 
            note=note
        )
        
    elif choice == '2':
        print("Operation rejected. The system correctly advised on viability.")

if __name__ == "__main__":
    run_nodal_app()