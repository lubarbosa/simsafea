/*
 *  SIMPLACE - Scientific Impact assessment and Modelling PLattform for Advanced Crop and Ecosystem management
 *
 *  This uses the SIMPLACE utility.
 *  
 *  This file may contain modules that are subject of copyright laws and have to be cited accordingly.
 *  
 *  SIMPLACE framework is free software: you can redistribute it and/or modify
 *  it under the terms of the GNU Lesser General Public License as published by
 *  the Free Software Foundation, either version 3 of the License, or
 *  (at your option) any later version.
 *  
 *  SIMPLACE is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU Lesser General Public License for more details.
 *  
 *  You should have received a copy of the GNU Lesser General Public License
 *  along with SIMPLACE.  If not, see <http://www.gnu.org/licenses/>.
 *  
 *  Komplett.java
 *
 *  Responsible developers: Gunther Krauss & Andreas Enders, Crop Science Group, Katzenburgweg 5, 53115 Bonn, Germany
 *  Contact Information:                    lap@uni-bonn.de
 */

package net.simplace.sim.tests.amit;

import net.simplace.core.logging.Logger;
import net.simplace.core.logging.Logger.LOGLEVEL;
import net.simplace.sim.FWSimEngine;
import net.simplace.sim.tests.SimplacerunStandardUnitTest;

import org.junit.Test;


/**
 * Test the lintul module
 * 
 * 
 */
public class AGRECO4CAST_AF extends SimplacerunStandardUnitTest
{
 
	/**
	 * SlimWater test: component ImprovedSoilWaterTWRHRZ  
	 */
	
	

	@Test
	public void AGRECO4CAST() 
	{
		Logger.setLogLevel(LOGLEVEL.DEBUG);
		String tProjectLines = "1";
		String tFileName = "${_WORKDIR_}/amit/AGROECO4CAST_AF/solution/AF_test.sol.xml";
		String tProjectFileName = "${_WORKDIR_}/amit/AGROECO4CAST_AF/project/AF_test.proj.xml";
		//FWSimEngine.runProjects(tProjectFileName, tFileName);
		
		try
		{
			runSimulation(tFileName, tProjectFileName, tProjectLines);
			//runSimulation(tFileName, tProjectFileName);
			runSimulation(tFileName);
		}
		catch (Exception aException)
		{
			Logger.ERROR("Problems ... ", aException, this);
			
		}
		
		
	}
	
	
	}		

