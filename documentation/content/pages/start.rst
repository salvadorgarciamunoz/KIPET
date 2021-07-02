Getting Started with KIPET
==========================

Creating a Model Instance
^^^^^^^^^^^^^^^^^^^^^^^^^

KIPET is comprised of many modules working in the background. Only two object classes are needed on the user's end. These are the ReactionModel and the ReactionLab classes.

All reactions are modeled as ReactionModel objects. If you are only considering a single reaction system or experiment, the simplest way to use KIPET is through a single ReactionModel instance. To do this, simply import the ReactionModel class from kipet and create an instance:
::

    from kipet import ReactionModel
    r1 = ReactionModel('model-1')
    

Model Components
^^^^^^^^^^^^^^^^
	
The ReactionModel class contains all of the methods necessary to use KIPET for a single model with a single dataset. You can now use the ReactionModel instance **r1** to add all of the expected model components such as the kinetic model and its parameters, the component information, and the data (if any). Parameters are added using the **parameter** method. For example, if we have a three component system with two reactions in series:

.. math::

	\mathrm{A} \xrightarrow{r_A} \mathrm{B} \xrightarrow{r_B} \mathrm{C}\\

.. math::

	\mathrm{r}_A = k_1C_A\\
	\mathrm{r}_B = k_2C_B
	

This system has two reactions and if we model them as simple first order reactions at constant temperature, we only have two parameters to fit: the reaction rate constants k1 and k2. This is done using the **parameter** method of the ReactionModel instance.
::

    k1 = r1.parameter('k1', value=2)
    k2 = r1.parameter('k2', value=0.2)

Thus, two parameter are added to **r1**: **k1** and **k2** with initial values 2 and 0.2, respectively. If you perform a simulation, these values will be the fixed parameter values in these models. For a full reference of parameter options, see :ref:`parameter`. 


Since our system has three components, A, B, and C, these need to be declared as well. In KIPET components are understood as being those species (chemicals or biological components) that are measured in concentrations. Components of this nature are added to the ReactionModel using the **component** method. More specifically, these are the components that can be measured using spectroscopic means. Under the hood, each component is treated as a state variable. Each component requires at least a name and an initial value. In our current example, the components can be defined as the following:
::

    A = r1.component('A', value=1)
    B = r1.component('B', value=0.0)
    C = r1.component('C', value=0.0)
	
Here you can see that only species A is present at the start of the reaction and the other components B and C are not.

If you were to add complementary states such as temperature, pressure, etc., this can be done using the **state** method. This should be used for all states that are not measured using concentration. For example, say there is a change in temperature during the reaction. In order to model this temperature change, you would need to add a temperature state variable to the model:
::

    T = r1.state('T', value=500, units='K')
	
Notice here that you can optionally add the units for any model component using the keyword argument units. KIPET has tools that ensure that units are converted to proper values and also checks for inconsistant unit types.

.. note::

    Every ReactionModel will have a volume state created automatically. This is to enusre that some features of KIPET that depend on volume always work properly. Thus, the variable name V is reserved for the volume state and an error will be raised if you try to name a model component with this name. If you need to modify the volume state (such as defining initial values and units), use the **volume** method.
    ::
	
	    r1.volume(value=0.45, units='mL') 

In the same manner, model constants can be generated. If you are using dimensionless units or do not care to check the units, you can simply add constants into the expressions (next section) using their numerical values. Suppose you have a constant feed to the reactor of species A of 2 moles per liter per minute. This could be added to the model using the following:
::

    C_Ain = r1.constant('C_Ain', value=2, units='M/min')
	
Another component that can be declared for use in a ReactionModel is a step function. The **step** method is a convenience way to add on/off decisions or steps during the reaction time. For example, if the constant feed rate of A given above is only to last for 5 minutes before being turned off, this behavior can be captured using a step component:
::

    A_step = r1.step('A_step', time=5, fixed=True, switch='off')
	
Here you can see the intuitive nature of adding step variables. The first argument is the name, followed by the time where the step occurs, whether the time is fixed at 5 or not (if False, it means that the step time is variable to be fit in the parameter estimation), and the direction of the step (in this case we turn the A feed off). The next step is simply to combine the flow rate of A with its step function during expression building.
::
    
	# The flowrate of A into the reactor is
	C_Ain * A_step
    
Step functions can be chained together for more complex on and off behaviors if needed. For example, if you needed to model that the flowrate of A into the reactor starts again at 10 minutes, this can be done in a similar manner as before:
::

    A_step_2 = r1.step('A_step', time=10, fixed=True, switch='on')

And then the steps can be combined into a single variable (actually an expression now):
::

    A_step_all = A_step + A_step_2
	
.. note::

    An improved version for chaining step functions is being worked on to simplify this procedure.
	
Expressions
^^^^^^^^^^^
	
For dynamic systems like chemical reactions, we necessarily work with ODEs. Each component and states is automatically assigned an accompanying ODE in KIPET with a default value of zero. If you forget to assign a more specific ODE, it will simply remain constant and not result in an error.
	
KIPET handles two types of expressions: ODEs and Algebraics. The key difference lies in how each is modeled in KIPET. In our current example, there are two reactions (A --> B and B --> C). These can be constructed as:
	
The next step is to provide the reaction kinetics. The five variables that were defined above (k1, k2, A, B, C) are all place holder Pyomo variables that can be used to construct expressions. This makes building expressions very simple in KIPET. Expressions can be used in either ODEs or algebraic expressions. There are several ways to add such expressions to KIPET.

::
    
    rA = k1 * A
    rB = k2 * B

or as
::

    rA = r1.add_reaction('rA', k1*A)
    rB = r1.add_reaction('rB', k2*B)
    
or equivalently
::
    
    rA = r1.add_expression('rA', k1*A, is_reaction=True)
    rB = r1.add_expression('rB', k2*B, is_reaction=True)
	
where the **add_reaction** method simply wraps the **add_expression** method and sets is_reaction to True for you. This syntax is simpler to use in creating the model. Once the reactions and other possible expressions have been generated, the ODEs can be created and added to the ReactionModel:
::
	
    r1.add_ode('A', -rA)
    r1.add_ode('B', rA - rB)
    r1.add_ode('C', rB)
	
If you would prefer to use a stoichiometric matrix to build the system of equations for the reactions, this is possible as well:
::

    rA = r1.add_reaction('rA', k1*A, description='Reaction A' )
    rB = r1.add_reaction('rB', k2*B, description='Reaction B' )
    
    stoich_data = {'rA': [-1, 1, 0],
                   'rB': [0, -1, 1]}
    
    r1.reactions_from_stoich(stoich_data, add_odes=True)
	
Note the form of the stoichiometric matrix. It takes the reaction name as the key and a list of stoichiometric coefficients as the the values. If you provide the keys as the components instead, KIPET will automatically detect this and still build the appropriate reaction network. The add_odes keyword argument is passed as True if the ODEs are based solely on the reaction kinetics. If you with to add additional terms to the ODEs (such as to account for volume changes), you need to set add_odes to False and use the returned dictionary of reaction ODEs to augment the expressions (see :ref:`Example5`).

For example, say we are feeding C to a reactor and need to take this into account after we have constructed the system of reactions using the stoiciometric matrix. Simply set add_odes to False and use the returned dictionary of ODEs (here RE) and simply add the volumetric change to the existing ODE. After you do this, the ODEs still need to be added to the ReactionModel which can be done using the **add_odes** method.
::

    RE = r1.reactions_from_stoich(stoich_coeff, add_odes=False)
    
    # Modify component C due to its changing volume
    RE['C'] += 0.02247311828 / (V * 210) * V_step
	
    r1.add_odes(RE)
	
.. note::

    You can still add additional ODEs to the ReactionModel afterwards. For example, if you need to add a volumetic flowrate (like the one influencing C above), this can be added in the usual manner using **add_ode**.
    
You may also generate the stoichiometric matrix from the finished system of ODEs using the **stoich_from_reactions** method. In order for this to work, you need to register the reactions using the **add_reaction** method. This becomes important for reactions involving unwanted contributions in the spectral data.

.. note::

    Volume changes are automatically applied to the ODEs for all components. This follows the form of
	
	.. math::
	
	    -\frac{\dot{V}}{V} \cdot C_i
		
		
	where :math:`V` is the volume state, :math:`\dot{V}` is the volume's rate of change (its ODE), and :math:`C_i` is the concentration of component :math:`i`.
	
.. note::

    You can disable the automatic generation of volume change terms in the settings:
	
	::
	
	    r1.settings.general.add_volume_terms = False


Experimental Data
^^^^^^^^^^^^^^^^^

KIPET has several features that make it very simple to add experimental data to the ReactionModel. Before showing how to add data to the model, it is important to know how to format the data and where KIPET expects the data to be found.

KIPET expects the data file to be in the same directory, or a subdirectory thereof, as the python script containing the model. If this is the case, then using the relative path to the data file is acceptable in your script.
::

    # Working directory
	
    reaction.py
    data/
        data_file.txt
		
The acceptable file in the example above is "data/data_file.txt". If the data is not in the project directory then the full path to the file should be used instead.
	
.. _data_format:
	
Data Formats
------------
		
The data can be stored as a *.txt* or *.csv* file. For state data, the data should be formatted using the component or state name in the column header and the times in the index (the first columns) with no header. KIPET takes the file type into account and formats the data appropriately.

For example:

.. figure:: ../images/csv_data.png
   :width: 600px
   :align: center

   How the data should be arranged for state data

If the data comes in the form of a *.txt* file, the data should be organized line for line like the following:
::

	time, component, measured value

    0.0, A, 0.0010270287422477187
    0.0, B, 0.0
    0.0, C, 1.2622004666719102e-05
    0.0333, A, 0.0010154146793560827
    0.0333, B, 2.2042495042078835e-06
    0.0333, C, 2.0555887807634343e-05
    0.0667, A, 0.001006906145441944
    0.0667, B, 1.3041463917576706e-05
    0.0667, C, 1.7636928106204522e-05
    0.1, A, 0.0009926352934163576
    0.1, B, 2.4680620670202026e-05
    0.1, C, 1.3762803314186124e-05
	etc...

Spectral data should have the first column contain the measurement times and the columns thereafter the wavelengths. See the image below for an example.

.. figure:: ../images/csv_spectral_data.png
   :width: 600px
   :align: center

   How the data should be arranged for spectral data
   
If the data comes in the form of a *.txt* file, the data should be organized line for line like the following:
::
 
    time, wavelength, measured value
	
    0.0000, 1610.00, 0.074030
    0.0000, 1620.00, 0.076191
    0.0000, 1630.00, 0.077368
    0.0000, 1640.00, 0.078412
    0.0000, 1650.00, 0.083268
    0.0000, 1660.00, 0.087972
    0.0000, 1670.00, 0.082916
    0.0000, 1680.00, 0.084603
    0.0000, 1690.00, 0.088627
    0.0000, 1700.00, 0.089958
    0.0000, 1710.00, 0.085465
    etc...
	
Adding the Data
---------------

The previous cases assumed that you were loading a datafile directly into KIPET. If this is the case, adding data is as simple as
::

    r1.add_data(file='data/data_file.txt')

using the same example as before.

If you wish to use your own data frame as data instead of loading directly from a file, this can be done by using the keyword argmument data:

::

	r1.add_data(data=<your_dataframe_goes_here>)

Also, you can use the methods **read_data** and **write_data** to load and write data in the KIPET format. These methods are accessible at the top-level:
::
 
    data_frame = kipet.read_data('filename')
    data_frame = data_frame.iloc[:, ::10]
    kipet.write_data('reduced_by_10_data.csv')
	
	
KIPET will automatically check if the entered components and states match with the column headers in the data added to the ReactionModel. It does not matter if the data is entered in before or after the components and states are declared. Once the data has been added to the ReactionModel, it can be accessed through the datasets attribute.
::

    r1.datasets['name_of_the_dataset']
	
Here the name of the dataset is either provided as the first positional argument to **add_data** or will be automatically generated based on the type of data added. For example, concentration data added without a name is named 'C_data'. State data is given the name 'U_data'. The dataset class contains a handful of methods that can be used to visualize the data, remove negative values, and more.

Due to the difference in structure of the spectral data, it is not found in the datasets attribute, but rather in the spectra attribute. The spectra attribute of the ReactionModel class is really a SpectralHandler object that contains various preprocessing tools as well as a plotting tool specifically designed for spectral data.

See the :ref:`add_data` method in ReactionModel for more information pertaining to other arguments and methods related to data in KIPET. Also checkout the :ref:`SpectraHandler` class and the :ref:`DataComponent` class to learn more about these objects and how to manage data in KIPET.

Simulation
^^^^^^^^^^

Once you have added all of the necessary components to the ReactionModel you are ready to perform simulation and/or parameter fitting. If you do not add any experimental data to the ReactionModel, you cannot proceed with parameter fitting and will only be able to perform simulations. In this case the simulator requires a start and an end time. In this case, the start time is generally zero and is not very important. The end time determines when the simulation will end and is therefore required. If you do provide experimental data with your simulation model, KIPET will automatically determine the end time based on the last measured data point. If you provide your own end time, this will override the time determined from the data.

::

    r1.set_time(10)

In the example above the end time is set at 10 (units can be derived from the base time unit configured using the ReactionModel).

Once the model is complete with the start and end times, running the simulation is as simple as
::
    r1.simulate()
	
The simulator in KIPET is based on a finite element by finite element approach to ensure robustness of the solution and a high chance of convergence.

.. note::

    If you have trouble simulating a model it may be the case that it is too stiff. Try increasing the number of finite elements in the model until it converges.
	
	::
	
	    r1.settings.collocation.nfe = <number of finite elements>

Parameter Fitting
^^^^^^^^^^^^^^^^^

The parameter fitting is also quite simple to use in KIPET. After the model is complete and includes experimental data, the parameter fitting can be started using the **run_opt** method.
::
    r1.run_opt()

Depending on the type of problem, a series of steps begins so that the solution to the parameter fitting problem can be found. It begins with a simulation no different from performing a stand-alone simulation. This is done using the initial values to provide the model with good initial values for the variables not defined by the user. These include the concentration profiles, absorbance profiles, and other variables. This greatly increases the speed of convergence and reduces the chance of having it fail to solve. If the reaction data contains spectral data, the variance estimation stage follows the simulation. Here, also depending on the method used to estimate the variances, the variance of each component is predicted from the spectral data and the model structure. After these variances are known, the parameter fitting may proceed. If only concentration data is present, the variances need to be provided to the model before the parameter fitting begins. Thus, problems with only concentration data jump straight to parameter fitting and do not require a variance estimation step. After the parameter estimation is complete, the results are stored in a ResultsObject that can be reached using the results attribute of the ReactionModel instance. All relevant variables are found here alongside their optimal trajectories in convenient data forms dependent upon the dimensionality of the data.

Also, once the results are available, there are many plotting tools that can be used to plot the various results obtained. This is accessed using the **plot** method of the ReactionModel class and takes the variable name in the model as the parameter. If no parameter is passed to **plot**, all plots related to the model are generated.

Plotting Results
^^^^^^^^^^^^^^^^

KIPET provides robust plotting methods that make it easy to display the results from simulation and parameter fitting problems. Plots are generated using the Plotly package and are saved as both HTML and SVG file types. The plot methods can be accessed simply by using the **plot** method. All plots are stored in a folder called "charts" that will be created in the working directory.
::

    r1.plot() # plots all related charts
    r1.plot('Z') # plots all concentration charts
    r1.plot('A') # plots the component A
    r1.plot('V') # plots the volume
    # and so on


.. _settings:

Settings
^^^^^^^^

If you happen to have used an earlier version of KIPET, you may have noticed that the user was responsible for entering in various options for the variance estimator, parameter estimation, multiple experiments estimator, and so on. In the latest version of KIPET, many of the options are maintained in the background with usually good default values for most problems. However, if you would like to change the default settings, you are free to do so. This can be done by accessing the Settings object through the settings attribute of the ReactionModel instance.

For example, you can change the number of collocation points and the number of finite elements by the following:
::
 
    r1.settings.collocation.ncp = 3
    r1.settings.collocation.nfe = 100
	
To see all options available, simply type r1.settings into the command prompt. The name in parathenses after the settings section title (i.e. General Settings (general)) is the name used to access this setting. For example, in the example above we change the collocation setting by accessing settings.collocation.ncp and settings.collocation.nfe, as can be seen below. In this way, the user can modify any of the settings using simple dot notation.
::
 
    >> r1.settings
	
	General Settings (general):
               confidence : 1
            initialize_pe : True
          no_user_scaling : True
         scale_parameters : False
                 scale_pe : True
          scale_variances : False
         simulation_times : None

	Unit Settings (units):
            concentration : M
                     time : hr
                   volume : L
				  
	Collocation Settings (collocation):
                   method : dae.collocation
                      ncp : 3
                      nfe : 60
                   scheme : LAGRANGE-RADAU
				   
	Simulation Settings (simulator):
                   solver : ipopt
                      tee : False
              solver_opts : {}

    # and many more...
	
If you would like to change the default values permanently, you can do this by changing the settings.yml file in the kipet directory.
