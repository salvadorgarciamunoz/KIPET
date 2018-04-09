#  _________________________________________________________________________
#
#  Kipet: Kinetic parameter estimation toolkit
#  Copyright (c) 2016 Eli Lilly.
#  _________________________________________________________________________

# Sample Problem 2 (From Sawall et.al.)
# First example from WF paper simulation of ODE system using pyomo discretization and IPOPT
#
#		\frac{dZ_a}{dt} = -k_1*Z_a	                Z_a(0) = 1
#		\frac{dZ_b}{dt} = k_1*Z_a - k_2*Z_b		Z_b(0) = 0
#               \frac{dZ_c}{dt} = k_2*Z_b	                Z_c(0) = 0

from kipet.model.TemplateBuilder import *
from kipet.sim.PyomoSimulator import *
from kipet.utils.data_tools import *
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sys

import pickle


if __name__ == "__main__":
        
    # create template model 
    builder = TemplateBuilder()    

    # components
    components = dict()
    components['AH']   = 0.395555
    components['B']    = 0.0351202
    components['C']    = 0.0
    components['BH+']  = 0.0
    components['A-']   = 0.0
    components['AC-']  = 0.0
    components['P']    = 0.0
        
    builder.add_mixture_component(components)

    # add algebraics
    algebraics = [0,1,2,3,4] # the indices of the rate rxns
    builder.add_algebraic_variable(algebraics)
    
    """
    # add parameters
    params = dict()
    params['k0'] = 5.0
    params['k1'] = 5.0
    params['k2'] = 1.0
    params['k3'] = 5.0
    params['k4'] = 1.0
    """
    params = dict()
    params['k0'] = 49.7796
    params['k1'] = 8.93156
    params['k2'] = 1.31765
    params['k3'] = 0.310870
    params['k4'] = 3.87809

    builder.add_parameter(params)

    # add additional state variables
    extra_states = dict()
    extra_states['V'] = 0.0629418
    
    builder.add_complementary_state_variable(extra_states)

    gammas = dict()
    gammas['AH']   = [-1, 0, 0,-1, 0]    
    gammas['B']    = [-1, 0, 0, 0, 1]   
    gammas['C']    = [ 0,-1, 1, 0, 0]  
    gammas['BH+']  = [ 1, 0, 0, 0,-1]   
    gammas['A-']   = [ 1,-1, 1, 1, 0] 
    gammas['AC-']  = [ 0, 1,-1,-1,-1]
    gammas['P']    = [ 0, 0, 0, 1, 1]
        
    def rule_algebraics(m,t):
        r = list()
        r.append(m.Y[t,0]-m.P['k0']*m.Z[t,'AH']*m.Z[t,'B'])
        r.append(m.Y[t,1]-m.P['k1']*m.Z[t,'A-']*m.Z[t,'C'])
        r.append(m.Y[t,2]-m.P['k2']*m.Z[t,'AC-'])
        r.append(m.Y[t,3]-m.P['k3']*m.Z[t,'AC-']*m.Z[t,'AH'])
        r.append(m.Y[t,4]-m.P['k4']*m.Z[t,'AC-']*m.Z[t,'BH+'])
        return r

    builder.set_algebraics_rule(rule_algebraics)

    def rule_odes(m,t):
        exprs = dict()
        eta = 1e-2
        step = 0.5*((t+1)/((t+1)**2+eta**2)**0.5+(210.0-t)/((210.0-t)**2+eta**2)**0.5)
        exprs['V'] = 7.27609e-05*step
        V = m.X[t,'V']
        # mass balances
        for c in m.mixture_components:
            exprs[c] = sum(gammas[c][j]*m.Y[t,j] for j in m.algebraics) - exprs['V']/V*m.Z[t,c]
            if c=='C':
                exprs[c] += 0.02247311828/(m.X[t,'V']*210)*step
        return exprs

    builder.set_odes_rule(rule_odes)
    
    filename =  'trimmed.csv'
    D_frame = read_spectral_data_from_csv(filename)
    meas_times = sorted(D_frame.index)

    #builder.add_measurement_times(meas_times)
    
    model = builder.create_pyomo_model(0,1400)    

    #model.pprint()
    
    sim = PyomoSimulator(model)
    # defines the discrete points wanted in the concentration profile
    sim.apply_discretization('dae.collocation',nfe=50,ncp=3,scheme='LAGRANGE-RADAU')

    # good initialization
    initialization = pd.read_csv("init_Z.csv",index_col=0)
    sim.initialize_from_trajectory('Z',initialization)
    initialization = pd.read_csv("init_X.csv",index_col=0)
    sim.initialize_from_trajectory('X',initialization)

    
    # simulate
    options = {}
    results = sim.run_sim('ipopt',
                          tee=True,
                          solver_opts=options)
    
    # display concentration results    
    results.Z.plot.line(legend=True)
    plt.xlabel("time (s)")
    plt.ylabel("Concentration (mol/L)")
    plt.title("Concentration Profile")

    results.Y.plot.line()
    plt.xlabel("time (s)")
    plt.ylabel("rxn rates (mol/L*s)")
    plt.title("Rates of rxn")
    plt.show()

    results.Z.to_csv("initialization.csv")