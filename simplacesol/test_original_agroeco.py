#!/usr/bin/env python3
"""
Test original AGROECO4CAST_AF solution with standard simplace.py
"""

import sys
sys.path.append("/home/hydros/.local/lib/python3.8/site-packages")

import simplace

# Paths
install_dir = "/home/hydros/Downloads/SIMPLACE"
work_dir = "/home/hydros/Downloads/SIMPLACE"
out_dir = "/home/hydros/Downloads/SIMPLACE/out"
solution_file = "/home/hydros/Downloads/SIMPLACE/AGROECO4CAST_AF/solution/AF_test.sol.xml"

print("Initializing SIMPLACE...")
sh = simplace.initSimplace(install_dir, work_dir, out_dir)
simplace.setLogLevel("WARN")

print("Opening project...")
simplace.openProject(sh, solution_file)

print("Creating simulation...")
sim = simplace.createSimulation(
    sh,
    {
        "projectid": "49662",
        "simulationid": "1",
        "startdate": "01.01.2020",
        "enddate": "02.01.2020",
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

print("Running simulation...")
simplace.runSimulations(sh)

print("Success! Simulation completed.")
result = simplace.result(sh, "FIRST", filter="CURRENT.DATE,Biomass.sTAGB")
if result:
    print(f"Results: {simplace.varmapToList(result)}")
else:
    print("No results available")
# Close
simplace.closeProject(sh)
