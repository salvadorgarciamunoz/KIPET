"""Example 3: Simulation using complementatry states with new KipetModel"""

# Standard library imports
import sys # Only needed for running the example from the command line

# Third party imports
from pyomo.core import exp

# Kipet library imports
from kipet import KipetModel

if __name__ == "__main__":

    with_plots = True
    if len(sys.argv)==2:
        if int(sys.argv[1]):
            with_plots = False

    kipet_model = KipetModel()
    
    r1 = kipet_model.new_reaction('reaction-1')
    
    # Declare the components and give the initial values
    r1.add_component('A', value=1.0)
    r1.add_component('B', value=0.0)
    r1.add_component('C', value=0.0)
    
    r1.add_state('T', value=290, description='Temperature')
    r1.add_state('V', value=100, description='Volumne')

    c = r1.get_model_vars()
    
    # Define the ODEs
    k1 = 1.25*exp((9500/1.987)*(1/320.0 - 1/c.T))
    k2 = 0.08*exp((7000/1.987)*(1/290.0 - 1/c.T))
    ra = -k1*c.A
    rb = 0.5*k1*c.A - k2*c.B
    rc = 3*k2*c.B
    cao = 4.0
    vo = 240
    T1 = 35000*(298 - c.T)
    T2 = 4*240*30.0*(c.T-305.0)
    T3 = c.V*(6500.0*k1*c.A - 8000.0*k2*c.B)
    Den = (30*c.A + 60*c.B + 20*c.C)*c.V + 3500.0
    
    r1.add_ode('A', ra + (cao - c.A)/c.V )
    r1.add_ode('B', rb - c.B*vo/c.V )
    r1.add_ode('C', rc - c.C*vo/c.V )
    r1.add_ode('T', (T1 + T2 + T3)/Den )
    r1.add_ode('V', vo )
    
    r1.set_times(0.0, 2.0)
    
    r1.settings.collocation.nfe = 20
    r1.settings.collocation.ncp = 1

    r1.simulate()  

    if with_plots:
        r1.plot()