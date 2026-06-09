#!/usr/bin/env python3
"""
Multi-cell AGROECO4CAST_AF controller with Hi-sAFe weather input
"""

import sys
sys.path.append("/home/hydros/.local/lib/python3.8/site-packages")

import simplace
from typing import List, Dict, Any
from dataclasses import dataclass
from typing import Optional


@dataclass
class CellWeather:
    """Weather data for one cell"""
    cell_rad: float  # J/m²/day
    tmin: float      # °C
    tmax: float      # °C
    wind: float      # m/s
    cell_rain: float # mm


def expand_stics_to_simplace_layers(stics_water):
    """
    Expand 5 STICS layers to 19 SIMPLACE layers
    
    STICS layers -> SIMPLACE layers:
    Layer 0 (0-40cm):   -> Layers 0-3   (0-10, 10-20, 20-30, 30-40)
    Layer 1 (40-80cm):  -> Layers 4-7   (40-50, 50-60, 60-70, 70-80)
    Layer 2 (80-140cm): -> Layers 8-13  (80-90, 90-100, 100-110, 110-120, 120-130, 130-140)
    Layer 3 (140-240cm)-> Layers 14-18 (140-150, 150-160, 160-170, 170-180, 180-190)
    Layer 4 (240-340cm)-> Not simulated (beyond 190cm)
    """
    simplace_water = []
    
    # Layer 0 (0-40cm) -> SIMPLACE layers 0-3
    for i in range(4):
        simplace_water.append(stics_water[0])
    
    # Layer 1 (40-80cm) -> SIMPLACE layers 4-7
    for i in range(4):
        simplace_water.append(stics_water[1])
    
    # Layer 2 (80-140cm) -> SIMPLACE layers 8-13
    for i in range(6):
        simplace_water.append(stics_water[2])
    
    # Layer 3 (140-240cm) -> SIMPLACE layers 14-18 (5 layers)
    for i in range(5):
        simplace_water.append(stics_water[3])
    
    return simplace_water  # 19 values total


class MultiCellAgroEcoController:
    
    def __init__(self, n_cells: int = 3, cell_ids: Optional[List[int]] = None):
        self.install_dir = "/home/hydros/Downloads/SIMPLACE"
        self.work_dir = "/home/hydros/Downloads/SIMPLACE"
        self.out_dir = "/home/hydros/Downloads/SIMPLACE/out"
        self.solution_file = "/home/hydros/Downloads/SIMPLACE/AGROECO4CAST_AF/solution/AF_test.sol.xml"
        self.n_cells = n_cells
        # Real Hi-sAFe cell IDs in the same order as the SIMPLACE simulations.
        # Defaults to 1..n_cells if not provided.
        self.cell_ids = cell_ids if cell_ids is not None else list(range(1, n_cells + 1))
        self.sh = None
        
        # Initialize log file
        self.log_file = "/home/hydros/Downloads/SIMPLACE/AGROECO4CAST_AF/simplace_outputs.txt"
        self._init_log_file()
        
        self._init_simplace()
        
        # ========== HI-SAFE SOIL WATER STATE FEEDBACK ==========
        # Store soil water from previous Hi-SAFE day for SIMPLACE initialization
        self.last_hisafe_soil_water: Dict[int, List[float]] = {}
        
        
    def _init_log_file(self):
        """Initialize the output log file with header"""
        with open(self.log_file, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("SIMPLACE Multi-Cell Output Log\n")
            f.write("=" * 80 + "\n")
            f.write(f"Number of cells: {self.n_cells}\n")
            f.write(f"Started: {self._get_timestamp()}\n")
            f.write("=" * 80 + "\n\n")
        
            # Write column headers
            f.write(f"{'Date':<12} {'Cell':<6} {'Biomass_t/ha':<15} {'LAI':<10} {'WSO_g/m2':<12} {'Root dep(m)':<12} {'DVS':<12} {'Crop WD (mm/day)':<12} {'N uptake (kg/ha)':<12} {'Crop ND (kg/ha)':<12}\n")
            f.write("-" * 80 + "\n")

    def _get_timestamp(self):
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def _init_simplace(self):
        """Initialize SIMPLACE and create n_cells simulations"""
        print(f"[SIMPLACE] Initializing AGROECO4CAST_AF with {self.n_cells} simulations...")
        
        self.sh = simplace.initSimplace(self.install_dir, self.work_dir, self.out_dir)
        simplace.setLogLevel("ERROR")
        simplace.openProject(self.sh, self.solution_file)
        
        # Create n_cells simulations with UNIQUE IDs
        for i in range(1, self.n_cells + 1):
            simplace.createSimulation(
                self.sh,
                {
                     "projectid": "49662",
                     "simulationid": str(i),  # CRITICAL: Unique per cell!
                     "startdate": "01.01.2000",  # Match Hi-sAFe year
                     "enddate": "31.12.2005",    # Full year
                     # Explicitly provide project variables
                     "vColumn": 452,
                     "vRow": 294,
                     "vLocationID": 49662,
                     "vlat": 52.36479534,
                     "vlon": 12.41872296,
                     "vNUTSID": "DE401",
                     "vSTATE_ID": "DE4",
                     "vSTATE_NAME": "Brandenburg",
                }
            )
        
        print(f"[SIMPLACE] Successfully initialized {self.n_cells} simulations\n")


    def set_soil_water_from_hisafe(self, soil_water_dict: Dict[int, List[float]]):
        """
        Store Hi-SAFE soil water state for SIMPLACE to use next day
        
        Args:
            soil_water_dict: Dict[cell_id] -> [5 STICS soil water values (%)]
        """
        self.last_hisafe_soil_water = soil_water_dict
        print(f"[SIMPLACE] Stored Hi-SAFE soil water for {len(soil_water_dict)} cells")
    
        
    def step_and_get_results(self, weather_data: List[CellWeather]) -> List[Dict[str, Any]]:
        """
        Step all simulations and extract multiple crop state variables.
    
        Returns:
            List of dicts with agronomic variables per cell
        """
        if len(weather_data) != self.n_cells:
            raise ValueError(f"Expected {self.n_cells} weather data, got {len(weather_data)}")

        # ========== UPDATE SOIL WATER FROM Hi-SAFE (PREVIOUS DAY) ==========
        if self.last_hisafe_soil_water:
            print("[SIMPLACE] Updating soil water from Hi-SAFE previous day")
            for cell_id in self.last_hisafe_soil_water:
                if cell_id in self.cell_ids:
                    print(f"  Cell {cell_id}: HR[0]={self.last_hisafe_soil_water[cell_id][0]:.2f}%")
        

        # Prepare parameters for all cells
        param_list = []
        for i, weather in enumerate(weather_data):
            param_list.append({
                "vCellRad": weather.cell_rad,
                "vTmin": weather.tmin,
                "vTmax": weather.tmax,
                "vWind": weather.wind,
                "vCellRain": weather.cell_rain,
            })
    
        # Define which variables to extract
        var_filter = [
            "CURRENT.DATE",
            "Biomass.sTAGB",      # Total aboveground biomass
            "Biomass.sLAI",       # Leaf area index
            "Biomass.sWSO",       # Yield_t_ha
            "Biomass.sRD",        # Max root depth
            "Phenology.sDVS",     # development stage of crop
            "SlimWater.PotentialEvapotranspiration", # crop water demand
            "NPKDemandSlimNP.sNUPTT", # total N uptake by crop
            "NPKDemandSlimNP.NDEMTO", # crop nitrogen demand
            # SOIL WATER BY LAYER (mm per layer @ 10cm intervals: 0->10cm, 1->20cm, ..., 18->190cm)
            "SlimWater.TotalVolumetricWaterContentPerLayer",  # Volumetric water content per layer
        ]
    
        # Step all simulations at once
        results_array = simplace.stepAllSimulations(
            self.sh,
            count=1,
            parameterlist=param_list,
            varFilter=var_filter,
        )

        # Parse results - convert Java objects to Python dicts
        results = []
        for i in range(self.n_cells):
            if i < len(results_array):
                # Convert SIMPLACE result to dict
                sim_data = simplace.varmapToList(results_array[i])
            else:
                sim_data = {}
        
            # Helper to safely extract values
            def safe_get(var_name, default=0.0):
                try:
                    val = sim_data.get(var_name, default)
                    # Handle potential type issues
                    if isinstance(val, (int, float)):
                        return float(val)
                    return default
                except:
                    return default
                    
            # Extract values
            date_val = sim_data.get("CURRENT.DATE", "")
            biomass_val = safe_get("Biomass.sTAGB", 0.0)
            lai_val = safe_get("Biomass.sLAI", 0.0)
            wso_val = safe_get("Biomass.sWSO", 0.0)
            dvs_val = safe_get("Phenology.sDVS", 0.0) 
            root_val = safe_get("Biomass.sRD", 0.0)  
            
            C_WD_val = safe_get("SlimWater.PotentialEvapotranspiration", 0.0) 
            P_NU_val = safe_get("NPKDemandSlimNP.sNUPTT", 0.0) 
            C_ND_val = safe_get("NPKDemandSlimNP.NDEMTO", 0.0)  
            
            
            # Extract soil water content by layer (19 layers @ 10cm intervals)
            soil_water_by_layer = []
            soil_water_raw = sim_data.get("SlimWater.TotalVolumetricWaterContentPerLayer", None)
            
            if soil_water_raw is not None:
                try:
                    # SIMPLACE returns array; convert to list
                    if hasattr(soil_water_raw, '__iter__') and not isinstance(soil_water_raw, str):
                        soil_water_by_layer = [float(x) for x in soil_water_raw]
                    else:
                        soil_water_by_layer = []
                except:
                    soil_water_by_layer = []
            
            # Ensure we have 19 layers (if fewer, pad with zeros)
            while len(soil_water_by_layer) < 19:
                soil_water_by_layer.append(0.0)
            soil_water_by_layer = soil_water_by_layer[:19]  # Take only first 19
            
            with open(self.log_file, "a") as f:
                soil_water_str = ",".join([f"{x:.2f}" for x in soil_water_by_layer])
                f.write(f"{date_val:<12} {i+1:<6} {biomass_val:<15.4f} {lai_val:<10.4f} {wso_val:<12.4f} {root_val:<12.4f} {dvs_val:<12.4f} {C_WD_val:<12.4f} {P_NU_val:<12.4f} {C_ND_val:<12.4f} soil_water={soil_water_str}\n")
        
            cell_result = {
                "cell": self.cell_ids[i],
                "date": sim_data.get("CURRENT.DATE", ""),
            
                # Biomass outputs [t/ha]
                "biomass": safe_get("Biomass.sTAGB", 0.0),
                "grain_biomass": safe_get("Biomass.sWSO", 0.0),
            
                # Morphology
                "lai": safe_get("Biomass.sLAI", 0.0),
                "root_depth_m": safe_get("Biomass.sRD", 0.0),
                
                # Phenology
                "dvs": safe_get("Phenology.sDVS", 0.0),
                
                # Water
                "water_demand_mm": safe_get("SlimWater.PotentialEvapotranspiration", 0.0),
                "soil_water_by_layer": soil_water_by_layer,  # NEW: List of 19 floats (mm)
                
                # Nitrogen
                "plant_n_kg_ha": safe_get("NPKDemandSlimNP.sNUPTT", 0.0),
                "n_demand_kg_ha": safe_get("NPKDemandSlimNP.NDEMTO", 0.0),
            }

            results.append(cell_result)
        
        return results

    # Keep backward compatibility
    def step_and_get_biomass(self, weather_data: List[CellWeather]) -> List[Dict[str, Any]]:
        """Legacy method - returns only biomass for backward compatibility"""
        results = self.step_and_get_results(weather_data)
        return [{"cell": r["cell"], "date": r["date"], "biomass": r["biomass"]} for r in results]
    
    def close(self):
        if self.sh:
            simplace.closeProject(self.sh)
            # Write footer to log file
            with open(self.log_file, "a") as f:
                f.write("\n" + "=" * 80 + "\n")
                f.write(f"Completed: {self._get_timestamp()}\n")
                f.write("=" * 80 + "\n")
        
            print(f"\n[SIMPLACE] Output logged to: {self.log_file}") 
            print("\n[SIMPLACE] Closed successfully")


# ============================================================================
# TEST WITH HI-SAFE WEATHER INPUTS
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Multi-Cell AGROECO4CAST_AF with Hi-sAFe Weather")
    print("=" * 60)
    
    ctrl = MultiCellAgroEcoController(n_cells=3)
    
    for day in range(1, 11):
        print(f"\n--- Day {day} ---")
        
        # Different weather per cell
        weather_data = [
            CellWeather(
                cell_rad=7_000_000.0 + i * 100_000,
                tmin=5.0 + i * 0.5,
                tmax=20.0 + i * 0.5,
                wind=2.5 + i * 0.2,
                cell_rain=0.0 if day % 3 != 0 else 5.0 + i
            )
            for i in range(3)
        ]
        
        results = ctrl.step_and_get_results(weather_data)
        
        for res in results:
            print(f"  Cell {res['cell']}: Date={res['date']}, "
                  f"Biomass={res['biomass']:.4f} t/ha, "
                  f"LAI={res['lai']:.4f}")
    
    ctrl.close()
    
    print("\n" + "=" * 60)
    print("✓ Test completed!")
    print("=" * 60)

