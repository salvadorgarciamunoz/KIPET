"""Example 2: Estimation with new KipetModel"""

# Standard library imports
import sys # Only needed for running the example from the command line

# Third party imports

# Kipet library imports
from kipet import KipetModel

if __name__ == "__main__":

    with_plots = True
    if len(sys.argv)==2:
        if int(sys.argv[1]):
            with_plots = False
 
    kipet_model = KipetModel()
    
    r1 = kipet_model.new_reaction('reaction-1')

    # Add the model parameters
    r1.add_parameter('k1', value=2, bounds=(0.0, 5.0))
    r1.add_parameter('k2', value=0.2, bounds=(0.0, 2.0))
    
    # Declare the components and give the initial values
    r1.add_component('A', value=1)
    r1.add_component('B', value=0.0)
    r1.add_component('C', value=0.0)
    
    # Use this function to replace the old filename set-up
    r1.add_data(category='spectral', file='example_data/Dij.txt')
    
    # Preprocessing!
    #r1.spectra.msc()
    r1.spectra.decrease_wavelengths(3)

    c = r1.get_model_vars()
    # define explicit system of ODEs
    rates = {}
    rates['A'] = -c.k1 * c.A
    rates['B'] = c.k1 * c.A - c.k2 * c.B
    rates['C'] = c.k2 * c.B
    
    r1.add_odes(rates)
    
    r1.bound_profile(var='S', bounds=(0, 10))

    # Settings
    r1.settings.collocation.ncp = 1
    r1.settings.collocation.nfe = 60
    r1.settings.parameter_estimator.tee = True
    r1.settings.parameter_estimator.solver = 'ipopt_sens'
    r1.settings.general.initialize_pe = True
    r1.settings.general.scale_pe = True
    
    # This is all you need to run KIPET!
    r1.run_opt()
    
    # Display the results
    r1.results.show_parameters
    
    # Plot results    
    if with_plots:
        r1.plot()