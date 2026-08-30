import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
import logging
from typing import Dict, Any, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Replanner:
    def __init__(self, roads_gdf: gpd.GeoDataFrame, current_hazards: pd.DataFrame, 
                 depots: list, villages: list, inventory: dict, demand: dict, commodities: list):
        self.roads_gdf = roads_gdf
        self.hazards_df = current_hazards
        self.depots = depots
        self.villages = villages
        self.inventory = inventory
        self.demand = demand
        self.commodities = commodities
        self.current_plan = None
        
    def _match_event_to_edge(self, event: Dict[str, Any]) -> str:
        try:
            pt = gpd.GeoDataFrame([{'geometry': Point(event['lon'], event['lat'])}], crs="EPSG:4326").to_crs(self.roads_gdf.crs)
            nearest_roads = gpd.sjoin_nearest(pt, self.roads_gdf, how="left", max_distance=500)
            return nearest_roads.iloc[0]['edge_id'] if not nearest_roads.empty else None
        except Exception as e:
            return None

    def _update_hazards(self, event: Dict[str, Any]) -> bool:
        edge_id = self._match_event_to_edge(event)
        if not edge_id: return False
            
        new_hazard = {
            'edge_id': edge_id,
            'blockage_pct': event.get('blockage_pct', 0.95),
            'est_clearance_hrs': event.get('est_clearance_hrs', 6.0),
            'risk_growth_per_hour': event.get('risk_growth_per_hour', 0.02)
        }
        self.hazards_df = self.hazards_df[self.hazards_df['edge_id'] != edge_id]
        self.hazards_df = pd.concat([self.hazards_df, pd.DataFrame([new_hazard])], ignore_index=True)
        return True

    def _calculate_delta(self, new_plan: Dict) -> Dict:
        if not self.current_plan: return {"status": "initial_plan", "data": new_plan}
        changes = []
        for key, new_qty in new_plan.get('allocations', {}).items():
            old_qty = self.current_plan.get('allocations', {}).get(key, 0)
            if new_qty != old_qty:
                changes.append({"depot_village_commodity": key, "old_qty": old_qty, "new_qty": new_qty, "action": "UPDATE" if old_qty > 0 else "NEW_ROUTE"})
        return {"status": "updated", "changes": changes, "shortfall": new_plan.get('shortfall')}

    def reoptimize(self, event: Dict[str, Any]) -> Tuple[bool, Dict]:
        if not self._update_hazards(event): return False, {"error": "Event could not be mapped"}
        try:
            new_plan = disaster_response_orchestrator(
                self.depots, self.villages, self.inventory, 
                self.demand, self.roads_gdf.drop(columns='geometry'), self.hazards_df, self.commodities
            )
            self.check_for_total_blockade(new_plan) # Alert govt if shortfall exists
            delta = self._calculate_delta(new_plan)
            self.current_plan = new_plan
            return True, delta
        except Exception as e:
            return False, {"error": str(e)}

    def inject_manual_hazard(self, manual_event: dict):
        edge_id = manual_event.get("edge_id")
        if not edge_id: return False
        self.hazards_df = self.hazards_df[self.hazards_df['edge_id'] != edge_id]
        self.hazards_df = pd.concat([self.hazards_df, pd.DataFrame([{
            'edge_id': edge_id,
            'blockage_pct': manual_event.get('blockage_pct', 0.95),
            'est_clearance_hrs': manual_event.get('est_clearance_hrs', 6.0),
            'risk_growth_per_hour': 0.02
        }])], ignore_index=True)
        return True

    def process_ai_prediction(self, ai_forecast_event: dict):
        """Scenario 5: AI predicts a flood in 48 hours. Preposition supplies NOW."""
        logging.info(f"AI Forecast received. Triggering prepositioning LP.")
        transport_cost = {(d, v): 10.0 for d in self.depots for v in self.villages}
        from ml.pipeline.preposition_lp import optimize_prepositioning
        preposition_plan = optimize_prepositioning(self.depots, self.villages, self.inventory, self.demand, transport_cost)
        if preposition_plan:
            logging.info(f"PREPOSITIONING ALERT: Moving {sum(preposition_plan.values())} units to safe zones.")
            return True, {"action": "preposition", "plan": preposition_plan}
        return False, {"error": "Prepositioning failed"}

    def check_for_total_blockade(self, new_plan: dict):
        """Alerts the government if the LP could not find any feasible road routes."""
        shortfall = new_plan.get("shortfall", {})
        if shortfall:
            logging.critical(f"CRITICAL ALERT: Total road blockade detected! Unmet demand: {shortfall}")
            # In production: trigger multilingual notifier for govt officials
            # The government will manually arrange airdrops/helicopters based on this alert.
            return True
        return False