# Standard library imports
from os import getcwd

# Third party imports
from pyomo.dae import ContinuousSet
from pyomo.environ import Constraint, ConstraintList, Param, TransformationFactory, value, Var
from pyomo.opt import ProblemFormat, SolverFactory, TerminationCondition

# KIPET library imports
from kipet.model_tools.visitor_classes import ReplacementVisitor
from kipet.general_settings.variable_names import VariableNames
from kipet.model_tools.pyomo_model_tools import (change_continuous_set,
                                                 get_index_sets)

__author__ = 'David M Thierry, Kevin McBride'  #: April 2018 - May 2021


class FEInitialize(object):
    """This class implements the finite per finite element initialization for
    a pyomo model initialization. A march-forward simulation will be run and 
    the resulting data will be patched to the tgt_model.
    
    The current strategy is as follows:
    1. Create a copy of the undiscretized model.
    2. Change the corresponding time set bounds to (0,1).
    3. Discretize and create the new model with the parameter h_i.
    4. Deactivate initial conditions.
    5. Check for params and inputs.

    
    .. note::
        
        An input needs to be a variable(fixed) indexed over time. Otherwise 
        it would be a parameter.

    """

    def __init__(self,
                 model_orig,
                 src_mod,
                 init_con=None,
                 param_name=None,
                 param_values=None,
                 inputs=None,
                 inputs_sub=None,
                 jump_times=None,
                 jump_states=None,
                 ):
        """
        The `the paran name` might be a list of strings or a single string
          corresponding to the parameters of the model.
        The `param_values` dictionary needs to be declared with the following 
        syntax: `param_dict["P", "k0"] = 49.7796`
        
        Where the first key corresponds to one of the parameter names, and the
        second to the corresponding index (if any).
        
        A similar structure is expected for the initial conditions and inputs.

        The `inputs` and `input_sub` parameters are in place depending of 
        whether there is a single index input or a multiple index input.

        Note that if the user does not provide correct information to 
        fe_factory; an exception will be thrown because of the n_var and m_eqn
        check for simulation.

        Once the constructor is called, one can initialize the model with the 
        following sintax: `self.load_initial_conditions(init_cond=ics_dict)`

        Finally, to run the initialization and automatic data patching to tgt
        model use: `self.run()`

        If a given finite element problem fails, we do will try once again with
        relaxed options. It is recommended to go back and check the model for 
        better understanding of the issue.

        Finally, an explicit function of time on the right hand side is 
        prohibited. Please put this information into an input (fixed variable)
        instead.

        :param ConcreteModel tgt_mod: The original fully discretized model that we want to patch the information to.
        :param ConcreteModel src_mod: The undiscretized reference model.
        :param str init_con: The initial constraint name (corresponds to a Constraint object).
        :param list param_name: The param name list. (Each element must correspond to a pyomo Var)
        :param dict param_values: The corresponding values: `param_dict["param_name", "param_index"] = 49.7796`
        :param dict inputs: The input dictionary. Use this dictonary for single index (time) inputs
        :param dict inputs_sub: The multi-index dictionary. Use this dictionary for multi-index inputs.
        
        """
        self.__var = VariableNames()

        self.ip = SolverFactory('ipopt')
        self.ip.options['halt_on_ampl_error'] = 'yes'
        self.ip.options['print_user_options'] = 'yes'

        self.model_orig = model_orig
        self.model_ref = src_mod.clone()

        self.volume_name = self.__var.volume_name
        if self.volume_name is None:
            raise ValueError('A volume name must exist')

        time_index = None
        for i in self.model_ref.component_objects(ContinuousSet):
            time_index = i
            break
        if time_index is None:
            raise Exception('no continuous_set')

        self.time_set = time_index.name

        model_original_time_set = getattr(self.model_orig, self.time_set)
        self.ncp = model_original_time_set.get_discretization_info()['ncp']
        fe_l = model_original_time_set.get_finite_elements()

        self.fe_list = [fe_l[i + 1] - fe_l[i] for i in range(0, len(fe_l) - 1)]
        self.nfe = len(self.fe_list)

        #: Re-construct the model with [0,1] time domain
        times = getattr(self.model_ref, self.time_set)
        change_continuous_set(times, [0, 1])

        for var in self.model_ref.component_objects(Var):
            var.clear()
            var.reconstruct()

        for con in self.model_ref.component_objects(Constraint):
            con.clear()
            con.construct()

        # self.model_ref.display(filename="selfmoddisc0.txt")
        #: Discretize
        d = TransformationFactory('dae.collocation')
        d.apply_to(self.model_ref, nfe=1, ncp=self.ncp, scheme='LAGRANGE-RADAU')

        #: Find out the differential variables
        self.dvs_names = []
        self.dvar_names = []

        for con in self.model_ref.component_objects(Constraint):
            name = con.name
            namel = name.split('_', 1)
            if len(namel) > 1:
                if namel[1] == "disc_eq":
                    realname = getattr(self.model_ref, namel[0])
                    self.dvar_names.append(namel[0])
                    self.dvs_names.append(realname.get_state_var().name)
        self.model_ref.h_i = Param(times, mutable=True, default=1.0)  #: Length of finite element

        #: Modify the collocation equations to introduce h_i (the length of finite element)
        for i in self.dvar_names:
            con = getattr(self.model_ref, i + '_disc_eq')
            dv = getattr(self.model_ref, i)
            e_dict = {}
            fun_tup = True
            for k in con.keys():
                if isinstance(k, tuple):
                    pass
                else:
                    k = (k,)
                    fun_tup = False
                e = con[k].expr.args[0]
                e_dict[k] = e * self.model_ref.h_i[k[0]] + dv[k] * (
                        1 - self.model_ref.h_i[k[0]]) == 0.0  #: As long as you don't clone
            if fun_tup:
                self.model_ref.add_component(i + "_deq_aug",
                                             Constraint(con.index_set(),
                                                        rule=lambda m, *j: e_dict[j] if j[
                                                                                            0] > 0.0 else Constraint.Skip))
            else:
                self.model_ref.add_component(i + "_deq_aug",
                                             Constraint(con.index_set(),
                                                        rule=lambda m, j: e_dict[j] if j > 0.0 else Constraint.Skip))
            self.model_ref.del_component(con)

        #: Sets for iteration
        #: Differential variables
        self.remaining_set = {}
        for i in self.dvs_names:
            dv = getattr(self.model_ref, i)
            if dv.index_set().name == times.name:  #: Just time set
                # print(i, 'here')
                self.remaining_set[i] = None
                continue
            # set_i = dv._implicit_subsets  #: More than just time set
            # set_i = dv._index._implicit_subsets #Update for pyomo 5.6.8 KH.L
            set_i = identify_member_sets(dv)
            # set_i = identify_member_sets(dv.index_set())
            # print(f'set_i = {set_i}')
            remaining_set = set_i[1]
            for s in set_i[2:]:
                remaining_set *= s
            if isinstance(remaining_set, list):
                self.remaining_set[i] = remaining_set
            else:
                self.remaining_set[i] = []
                self.remaining_set[i].append(remaining_set)
        #: Algebraic variables
        self.weird_vars = []  #:Not indexed by time
        self.remaining_set_alg = {}
        # with open('model_check.txt', 'w') as f5:
        #     self.model_ref.pprint(ostream = f5)
        for av in self.model_ref.component_objects(Var):

            # print(av.name)
            if av.name in self.dvs_names:
                continue
            if av.index_set().name == times.name:  #: Just time set
                self.remaining_set_alg[av.name] = None
                continue
            # set_i = av._implicit_subsets
            # set_i = av._index._implicit_subsets #Update for pyomo 5.6.8 KH.L
            set_i = identify_member_sets(av)
            if set_i is None or not times in set_i:
                self.weird_vars.append(av.name)  #: Not indexed by time!
                continue  #: if this happens we might be in trouble
            remaining_set = set_i[1]  #: Index by time and others
            for s in set_i[2:]:
                if s.name == times.name:
                    self.remaining_set_alg[av.name] = None
                    continue
                else:
                    remaining_set *= s
            if isinstance(remaining_set, list):
                self.remaining_set_alg[av.name] = remaining_set
            else:
                self.remaining_set_alg[av.name] = []
                self.remaining_set_alg[av.name].append(remaining_set)

        if init_con is not None:  #: Delete the initial conditions (we use .fix() instead)
            ic = getattr(self.model_ref, init_con)
            self.model_ref.del_component(ic)

        if isinstance(param_name, list):  #: Time independent parameters
            if param_values:
                if isinstance(param_values, dict):
                    for pname in param_name:
                        p = getattr(self.model_ref, pname)
                        for key in p.keys():
                            try:
                                val = param_values[pname, key]
                                p[key].set_value(val)
                            except KeyError:
                                raise Exception("Missing a key of the param_values\n"
                                                "Please provide all the required keys.\n"
                                                "missing: {}".format(key))
                            p[key].fix()
                else:
                    Exception("Arg param_values should be provided in a dictionary")
            else:
                Exception("Arg param_values should be provided in a dictionary")
        elif isinstance(param_name, str):
            if param_values:
                if isinstance(param_values, dict):
                    p = getattr(self.model_ref, param_name)
                    for key in p.keys():
                        try:
                            val = param_values[param_name, key]
                            p[key].set_value(val)
                        except KeyError:
                            raise Exception("Missing a key of the param_values\n"
                                            "Please provide all the required keys.\n"
                                            "missing: {}".format(key))
                        p[key].fix()
        elif not param_name:
            pass
        else:
            raise Exception("wrong type for param_name")

        #: Fix initial conditions
        for i in self.dvs_names:
            dv = getattr(self.model_ref, i)
            if self.remaining_set[i] is None:
                dv[0].fix()
            for rs in self.remaining_set[i]:
                for k in rs:
                    k = k if isinstance(k, tuple) else (k,)
                    dv[(0,) + k].fix()

        self.inputs = None
        self.input_remaining_set = {}

        #: Check if inputs are declared
        # if self.inputs is not None:
        #     if not isinstance(inputs, dict) or isinstance(inputs, str):
        #         raise Exception("Must be a dict or str")
        #     if isinstance(inputs, str):
        #         self.inputs = [self.inputs]
        #     for i in self.inputs:
        #         p = getattr(self.model_ref, i)
        #         p.fix()
        #         if p.index_set().name == times.name:  #: Only time-set
        #             self.input_remaining_set[i] = None
        #             continue
        #         #set_i = p._implicit_subsets
        #         #set_i = p._index._implicit_subsets #Update for pyomo 5.6.8 KH.L
        #         set_i = identify_member_sets(p)
        #         if not times in set_i:
        #             raise RuntimeError("{} is not by index by time, this can't be an input".format(i))
        #         remaining_set = set_i[1]
        #         for s in set_i[2:]:
        #             if s.name == times.name:  #: would this ever happen?
        #                 continue
        #             else:
        #                 remaining_set *= s
        #         if isinstance(remaining_set, list):
        #             self.input_remaining_set[i] = remaining_set
        #         else:
        #             self.input_remaining_set[i] = []
        #             self.input_remaining_set[i].append(remaining_set)

        # self.inputs_sub = None
        # inputs_sub['some_var'] = ['index0', 'index1', ('index2a', 'index2b')]

        self.inputs_sub = inputs_sub
        # print([i.name for i in get_index_sets(getattr(self.model_ref, 'Dose'))])

        if self.inputs_sub is not None:
            for key in self.inputs_sub.keys():
                model_var_obj = getattr(self.model_ref, key)

                # This finds the index of the set    
                # if identify_member_sets(model_var_obj) is None:
                #     raise RuntimeError("This variable is does not have multiple indices"
                #                         "Pass {} as part of the inputs keyarg instead.".format(key))
                # elif model_var_obj.index_set().name == times.name:
                #     raise RuntimeError("This variable is indexed over time"
                #                         "Pass {} as part of the inputs keyarg instead.".format(key))
                # else:
                #     if times not in identify_member_sets(model_var_obj):
                #         raise RuntimeError("{} is not indexed over time; it can not be an input".format(key))

                for k in self.inputs_sub[key]:
                    if isinstance(k, str) or isinstance(k, int) or isinstance(k, tuple):
                        k = (k,) if not isinstance(k, tuple) else k
                    else:
                        raise RuntimeError("{} is not a valid index".format(k))

                    for t in times:
                        model_var_obj[(t,) + k].fix()

        if hasattr(self.model_ref, self.__var.time_step_change):
            for time_step in getattr(self.model_ref, self.__var.time_step_change):
                getattr(self.model_ref, self.__var.time_step_change)[time_step].fix()

        if hasattr(self.model_ref, self.__var.model_constant):
            for param, obj in getattr(self.model_ref, self.__var.model_constant).items():
                obj.fix()

        # if hasattr(self.model_ref, self.__var.algebraic):
        #     model_var_obj = getattr(self.model_ref, self.__var.algebraic)
        #     for k in ['f']:
        #         if isinstance(k, str) or isinstance(k, int) or isinstance(k, tuple):
        #             k = (k,) if not isinstance(k, tuple) else k
        #         else:
        #             raise RuntimeError("{} is not a valid index".format(k))
        #         for t in times:
        #             print(model_var_obj.display())
        #             model_var_obj[(t,) + k].fix()

        # for param, obj in getattr(self.model_ref, self.__var.algebraic).items():
        #     print(param)
        #     print(obj)
        #     if param[1] == 'f' or param[1] == 'Csat':
        #         for t in times:
        #             print(t, param[1])
        #             obj[(t,) + (param[1],)].fix()

        # : Check n vars and m equations
        (n, m) = reconcile_nvars_mequations(self.model_ref)
        if n != m:
            raise Exception("Inconsistent problem; n={}, m={}".format(n, m))
        self.jump = False
        self.con_num = 0

    def load_initial_conditions(self, init_cond=None):
        if not isinstance(init_cond, dict):
            raise Exception("init_cond must be a dictionary")

        for i in self.dvs_names:
            dv = getattr(self.model_ref, i)
            ts = getattr(self.model_ref, self.time_set)  # self.model_ref.alltime
            for t in ts:
                for s in self.remaining_set[i]:
                    if s is None:
                        val = init_cond[i]  #: if you do not have an extra index, just put the value there
                        dv[t].set_value(val)
                        if t == 0:
                            if not dv[0].fixed:
                                dv[0].fix()
                        continue
                    for k in s:
                        val = init_cond[i, k]
                        k = k if isinstance(k, tuple) else (k,)
                        dv[(t,) + k].set_value(val)
                        if t == 0:
                            if not dv[(0,) + k].fixed:
                                dv[(0,) + k].fix()

    def march_forward(self, fe):
        """Moves forward with the simulation.

        This method performs the actions required for setting up the `fe-th` problem.

        Adjust inputs.
        Solve current problem.
        Patches tgt_model.
        Cycles initial conditions

        :param int fe: The corresponding finite element.

        :return: None

        """
        self.adjust_h(fe)
        if self.inputs or self.inputs_sub:
            self.load_input(fe)

        self.ip.options["print_level"] = 1  #: change this on demand
        # self.ip.options["start_with_resto"] = 'no'
        self.ip.options['bound_push'] = 1e-02
        sol = self.ip.solve(self.model_ref, tee=False, symbolic_solver_labels=True)

        # Try to redo it if it fails
        if sol.solver.termination_condition != TerminationCondition.optimal:
            self.ip.options["OF_start_with_resto"] = 'yes'

            sol = self.ip.solve(self.model_ref, tee=False, symbolic_solver_labels=True)
            if sol.solver.termination_condition != TerminationCondition.optimal:

                self.ip.options["OF_start_with_resto"] = 'no'
                self.ip.options["bound_push"] = 1E-02
                self.ip.options["OF_bound_relax_factor"] = 1E-05
                sol = self.ip.solve(self.model_ref, tee=True, symbolic_solver_labels=True)
                self.ip.options["OF_bound_relax_factor"] = 1E-08

                # It if fails twice, raise an error
                if sol.solver.termination_condition != TerminationCondition.optimal:
                    raise Exception("The current iteration was unsuccessful. Iteration :{}".format(fe))

        self.patch(fe)
        self.cycle_ics(fe)

    def load_discrete_jump(self, dosing_points):
        """Method is used to define and load the places where discrete jumps are located, e.g.
        dosing points or external inputs.

        :param list dosing_points: A list of DosingPoint objects

        :return: None

        """
        self.jump = True
        self.dosing_points = dosing_points

        return None

    def cycle_ics(self, curr_fe):
        """Cycles the initial conditions of the initializing model.
        Take the values of states (initializing model) at t=last and patch them into t=0.
        Check: :ref:`<https://github.com/dthierry/cappresse/blob/pyomodae-david/nmpc_mhe/aux/utils.py>`_
        fe_cp function!

        :param int curr_fe: The current finite element

        :return: None

        """
        ts = getattr(self.model_ref, self.time_set)
        t_last = t_ij(ts, 0, self.ncp)

        # Inclusion of discrete jumps: (CS)
        for i in self.dvs_names:
            dv = getattr(self.model_ref, i)
            for s in self.remaining_set[i]:
                if s is None:
                    val = value(dv[t_last])
                    dv[0].set_value(val)
                    if not dv[0].fixed:
                        dv[0].fix()
                    continue
                for k in s:
                    k = k if isinstance(k, tuple) else (k,)
                    val = value(dv[(t_last,) + k])
                    dv[(0,) + k].set_value(val)
                    if not dv[(0,) + k].fixed:
                        dv[(0,) + k].fix()

    def patch(self, fe):
        """ Take the current state of variables of the initializing model at fe and load it into the tgt_model
        Note that this will skip fixed variables as a safeguard.

        :param int fe: The current finite element to be patched (tgt_model).

        :return: None

        """
        time_set_ref = getattr(self.model_ref, self.time_set)
        time_set_orig = getattr(self.model_orig, self.time_set)

        for model_ref_var in self.model_ref.component_objects(Var, active=True):
            model_orig_var = getattr(self.model_orig, model_ref_var.name)
            if model_ref_var.name in self.weird_vars:
                for k in model_ref_var.keys():
                    if model_ref_var[k].stale or model_ref_var[k].is_fixed():
                        continue
                    try:
                        val = model_ref_var[k].value
                    except ValueError:
                        pass
                    model_ref_var[k].set_value(val)
                continue
            #: From this point on all variables are indexed over time.
            if model_ref_var.name in self.dvs_names:
                drs = self.remaining_set[model_ref_var.name]
            else:
                drs = self.remaining_set_alg[model_ref_var.name]

            for j in range(0, self.ncp + 1):

                t_tgt = t_ij(time_set_orig, fe, j)
                t_src = t_ij(time_set_ref, 0, j)

                if drs is None:
                    if model_ref_var[t_src].stale or model_ref_var[t_src].is_fixed():
                        continue
                    try:
                        val = model_ref_var[t_src].value
                    except ValueError:
                        print("Error at {}, {}".format(model_ref_var.name, t_src))
                    model_ref_var[t_tgt].set_value(val)
                    continue

                for k in drs:
                    for key in k:
                        key = key if isinstance(key, tuple) else (key,)
                        if model_ref_var[(t_src,) + key].stale or model_ref_var[(t_src,) + key].is_fixed():
                            continue
                        try:
                            val = value(model_ref_var[(t_src,) + key])
                        except ValueError:
                            print("Error at {}, {}".format(model_ref_var.name, (t_src,) + key))
                        model_orig_var[(t_tgt,) + key].set_value(val)

        if self.jump:

            """This creates a new constraint forcing the variable at the
            specific time to be equal to step size provided in the dosing
            points. It creates the constraint and replaces the variable in the
            original ode equations.
            """
            vs = ReplacementVisitor()
            for model_var, dosing_point_list in self.dosing_points.items():

                for dosing_point in dosing_point_list:

                    self.jump_fe, self.jump_cp = fe_cp(time_set_orig, dosing_point.time)
                    comp_dict = self.make_comp_list()

                    if fe == self.jump_fe + 1:

                        for comp_tuple in comp_dict:
                            model_var = comp_tuple[0]
                            comp = comp_tuple[1]
                            con_name = f'd{model_var}dt_disc_eq'
                            varname = f'{model_var}_dummy_{self.con_num}'
                            conc_delta = self.concentration_calc(dosing_point)

                            # This is the constraint you want to change (add dummy for the model_var)
                            model_con_obj = getattr(self.model_orig, con_name)

                            # Adding some kind of constraint to the list
                            self.model_orig.add_component(f'{model_var}_dummy_eq_{self.con_num}_{comp}',
                                                          ConstraintList())
                            model_con_objlist = getattr(self.model_orig, f'{model_var}_dummy_eq_{self.con_num}_{comp}')

                            # Adding a variable (no set) with dummy name to model
                            self.model_orig.add_component(varname, Var([0]))

                            # vdummy is the var_obj of the Var you just made
                            vdummy = getattr(self.model_orig, varname)

                            # this is the variable that will replace the other
                            vs.change_replacement(vdummy[0])

                            # adding a parameter that is the jump at dosing_point.step (the size or change in the var)
                            self.model_orig.add_component(f'{model_var}_jumpdelta{self.con_num}_{comp}',
                                                          Param(initialize=conc_delta[comp]))

                            # This is the param you just made
                            jump_param = getattr(self.model_orig, f'{model_var}_jumpdelta{self.con_num}_{comp}')

                            # This is where the new concentrations need to be calculated - start with A
                            # jump_param is what needs to be modified

                            # Constraint setting the variable equal to the step size
                            exprjump = vdummy[0] - getattr(self.model_orig, model_var)[
                                (dosing_point.time,) + (comp,)] == jump_param

                            # Add the new constraint to the original model
                            self.model_orig.add_component(f'jumpdelta_expr{self.con_num}_{comp}',
                                                          Constraint(expr=exprjump))

                            for kcp in range(1, self.ncp + 1):
                                curr_time = t_ij(time_set_orig, self.jump_fe + 1, kcp)
                                idx = (curr_time,) + (comp,)
                                model_con_obj[idx].deactivate()
                                var_expr = model_con_obj[idx].expr
                                suspect_var = var_expr.args[0].args[1].args[0].args[0].args[1]
                                vs.change_suspect(id(suspect_var))  #: who to replace
                                e_new = vs.dfs_postorder_stack(var_expr)  #: replace
                                model_con_obj[idx].set_value(e_new)
                                model_con_objlist.add(model_con_obj[idx].expr)

                            self.con_num += 1

    def make_comp_list(self):
        """Creates a list of tuples to pair model variables with component
        and volume variables
        
        :return list comp_dict: A list of tuples
        
        """
        comp_dict = []
        for comp in self.model_orig.mixture_components.keys():
            comp_dict.append((self.__var.concentration_model, comp))
        comp_dict.append((self.__var.state_model, self.volume_name))
        return comp_dict

    def concentration_calc(self, dosing_point):
        """This method calculates the changes in the concentration when 
        adding a volume of substance with specified concentrations of species
        
        :param DosingPoint dosing_point: Takes a dosing point object
        
        :return dict delta_conc: A dict of tuples with the component and 
          step change in concentration. This includes the volume step too.
        
        .. note::
            
            This only takes a single species at the moment. Use multiple dosing
            points if you need to add mixtures at the same point.
            
        """
        time_set_orig = getattr(self.model_orig, self.time_set)

        # Get the current time point
        curr_time = t_ij(time_set_orig, self.jump_fe + 1, 1)

        # Get the current volume
        vol = getattr(self.model_orig, self.__var.state_model)[(curr_time,) + (self.volume_name,)].value

        # Get the current concentrations
        conc = {}
        for comp in list(self.model_orig.mixture_components.keys()):
            conc[comp] = getattr(self.model_orig, self.__var.concentration_model)[(curr_time,) + (comp,)].value

        # Calculate the moles of each substance at the current point
        moles = {}
        for comp in conc:
            moles[comp] = vol * conc[comp]

        conc_change = dosing_point.conc[0]
        vol_change = dosing_point.vol[0]

        # Add the dosing point to the moles
        moles[dosing_point.component] += conc_change * vol_change
        vol += vol_change
        delta_conc = {k: v / vol - conc[k] for k, v in moles.items()}
        delta_conc[self.volume_name] = vol_change

        return delta_conc

    def adjust_h(self, fe):
        """Adjust the h_i parameter of the initializing model.

        The initializing model goes from t=(0,1) so it needs to be scaled by the current time-step size.

        :param int fe: The current value of h_i

        :return: None

        """
        hi = getattr(self.model_ref, "h_i")
        zeit = getattr(self.model_ref, self.time_set)
        for t in zeit:
            hi[t].value = self.fe_list[fe]

    def run(self, resto_strategy="bound_relax"):
        """Runs the sequence of problems fe=0,nfe

        :param str resto_strategy: The restoration strategy for the march_forward algorithm

        :return: None

        """
        for i in range(0, len(self.fe_list)):
            self.march_forward(i)

    def load_input(self, fe):
        """ Loads the current value of input from tgt_model into the initializing model at the current fe.

        :param int fe:  The current finite element to be loaded.

        :return: None

        """
        if self.inputs is not None:
            time_set_ref = getattr(self.model_ref, self.time_set)
            time_set_orig = getattr(self.model_orig, self.time_set)
            for i in self.inputs:
                p_data = getattr(self.model_orig, i)
                p_sim = getattr(self.model_ref, i)
                if self.input_remaining_set[i] is None:
                    for j in range(0, self.ncp + 1):
                        t = t_ij(time_set_orig, fe, j)
                        tsim = t_ij(time_set_ref, 0, j)
                        val = value(p_data[t])
                        p_sim[tsim].set_value(val)
                    continue
                for k in self.input_remaining_set[i]:
                    for key in k:
                        for j in range(0, self.ncp + 1):
                            t = t_ij(time_set_orig, fe, j)
                            tsim = t_ij(time_set_ref, 0, j)
                            val = value(p_data[(t,) + key])
                            p_sim[(tsim,) + key].set_value(val)

        # Here is where the jumps come in... (can this be done with a different var?)
        if self.inputs_sub is not None:
            time_set_ref = getattr(self.model_ref, self.time_set)
            time_set_orig = getattr(self.model_orig, self.time_set)

            for key in self.inputs_sub.keys():  # Y
                model_orig_var = getattr(self.model_orig, key)
                model_ref_var = getattr(self.model_ref, key)

                for sub_key in self.inputs_sub[key]:
                    sub_key = (sub_key,) if not isinstance(sub_key, tuple) else k

                    for j in range(0, self.ncp + 1):
                        t_orig = t_ij(time_set_orig, fe, j)
                        t_ref = t_ij(time_set_ref, 0, j)
                        val = model_orig_var[(t_orig,) + sub_key].value
                        model_ref_var[(t_ref,) + sub_key].set_value(val)

    def create_bounds(self, bound_dict):
        time_set_ref = getattr(self.model_ref, self.time_set)
        for v in bound_dict.keys():
            var = getattr(self.model_ref, v)
            varbnd = bound_dict[v]
            if not isinstance(varbnd, dict):
                raise RuntimeError("The entry for {} is not a dictionary".format(v))
            for t in time_set_ref:
                for k in varbnd.keys():
                    bnd = varbnd[k]
                    if not isinstance(k, tuple):
                        k = (k,)
                    var[(t,) + k].setlb(bnd[0])  #: Lower bound
                    var[(t,) + k].setub(bnd[1])  #: Upper bound

    def clear_bounds(self):
        for v in self.model_ref.component_data_objects(Var):
            v.setlb(None)
            v.setub(None)


def t_ij(time_set, i, j):
    # type: (ContinuousSet, int, int) -> float
    """Return the corresponding time(continuous set) based on the i-th finite element and j-th collocation point
    From the NMPC_MHE framework by @dthierry.

    :param ContinuousSet time_set: Parent Continuous set
    :param int i: finite element
    :param int j: collocation point

    :return: Corresponding index of the ContinuousSet
    :rtype: float

    """
    if i < time_set.get_discretization_info()['nfe']:
        h = time_set.get_finite_elements()[i + 1] - time_set.get_finite_elements()[i]  #: This would work even for 1 fe
    else:
        h = time_set.get_finite_elements()[i] - time_set.get_finite_elements()[i - 1]  #: This would work even for 1 fe
    tau = time_set.get_discretization_info()['tau_points']
    fe = time_set.get_finite_elements()[i]
    time = fe + tau[j] * h
    return round(time, 6)


def write_nl(d_mod, filename=None):
    """
    Write the nl file

    :param ConcreteModel d_mod: the model of interest.

    :return str cwd: The current working directory.

    """
    if not filename:
        filename = d_mod.name + '.nl'
    d_mod.write(filename, format=ProblemFormat.nl,
                io_options={"symbolic_solver_labels": True})
    cwd = getcwd()
    # print("nl file {}".format(cwd + "/" + filename))
    return cwd


def reconcile_nvars_mequations(d_mod):
    """
    Compute the actual number of variables and equations in a model by reading the relevant line at the nl file.

    :param ConcreteModel d_mod: the model of interest.

    :return tuple: The number of variables and the number of constraints.

    """
    fullpth = getcwd()
    fullpth += "/_reconciled.nl"
    write_nl(d_mod, filename=fullpth)
    with open(fullpth, 'r') as nl:
        lines = nl.readlines()
        line = lines[1]
        newl = line.split()
        nvar = int(newl[0])
        meqn = int(newl[1])
        nl.close()

    return (nvar, meqn)


def disp_vars(model, file):
    """Helper function for debugging

    :param ConcreteModel model: the model of interest.
    :param str file: Destination text file.

    :return: None

    """
    with open(file, 'w') as f:
        for c in model.component_objects(Var):
            c.pprint(ostream=f)
        f.close()


def fe_cp(time_set, feedtime):
    """Return the corresponding fe and cp for a given time

    :param ContinuousSet time_set: The time index
    :param float feedtime: The time of the dosing point

    :return: tuple of the finite element and the collocation point

    """
    fe_l = time_set.get_lower_element_boundary(feedtime)
    fe = None
    j = 0
    for i in time_set.get_finite_elements():
        if fe_l == i:
            fe = j
            break
        j += 1
    h = time_set.get_finite_elements()[1] - time_set.get_finite_elements()[0]
    tauh = [i * h for i in time_set.get_discretization_info()['tau_points']]
    j = 0  #: Watch out for LEGENDRE
    cp = None
    for i in tauh:
        if round(i + fe_l, 6) == feedtime:
            cp = j
            break
        j += 1
    return fe, cp


def identify_member_sets(model_var_obj):
    """Identifies the index sets of the given variable

    :param GeneralVar model_var_obj: The variable object of the model

    :return: None or the list of indices

    """
    index_list = get_index_sets(model_var_obj)

    if len(index_list) > 1:
        return index_list
    else:
        return None
