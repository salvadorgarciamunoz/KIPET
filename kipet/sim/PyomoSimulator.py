from pyomo.environ import *
from pyomo.dae import *
from ResultsObject import *
from Simulator import *


class PyomoSimulator(Simulator):
    def __init__(self,model):
        super(PyomoSimulator, self).__init__(model)
        self._times = sorted(self.model.time)
        self._n_times = len(self._times)
        self._spectra_given = hasattr(self.model, 'D')
        self._ipopt_scaled = False
        # creates scaling factor suffix
        self.model.scaling_factor = Suffix(direction=Suffix.EXPORT)
        
    def apply_discretization(self,transformation,**kwargs):
        discretizer = TransformationFactory(transformation)
        discretizer.apply_to(self.model,wrt=self.model.time,**kwargs)
        self._times = sorted(self.model.time)
        self._n_times = len(self._times)
        self._discretized = True
        
    def initialize_from_trajectory(self,variable_name,trajectories):
        if self._discretized is False:
            raise RuntimeError('apply discretization first before runing simulation')
        
        if variable_name == 'Z':
            var = self.model.Z
            inner_set = self.model.time
        elif variable_name == 'dZdt':
            var = self.model.dZdt
            inner_set = self.model.time
        elif variable_name == 'C':
            var = self.model.C
            inner_set = self._meas_times
        elif variable_name == 'S':
            var = self.model.S
            inner_set = self._meas_lambdas
        else:
            raise RuntimeError('Initialization of variable {} is not supported'.format(variable_name))

        mixture_components = trajectories.columns
        
        for component in mixture_components:
            if component not in self._mixture_components:
                raise RuntimeError('Mixture component {} is not in model mixture components'.format(component))

        trajectory_times = np.array(trajectories.index)
        n_ttimes = len(trajectory_times)
        first_time = trajectory_times[0]
        last_time = trajectory_times[-1]
        for component in mixture_components:
            for t in inner_set:
                if t>=first_time and t<=last_time:
                    idx = find_nearest(trajectory_times,t)
                    t0 = trajectory_times[idx]
                    if t==t0:
                        var[t,component].value = trajectories[component][t0]
                    else:
                        if t0==last_time:
                            var[t,component].value = trajectories[component][t0]
                        else:
                            idx1 = idx+1
                            t1 = trajectory_times[idx1]
                            x_tuple = (t0,t1)
                            y_tuple = (trajectories[component][t0],trajectories[component][t1])
                            y = interpolate_linearly(t,x_tuple,y_tuple)
                            var[t,component].value = y

    def scale_variables_from_trajectory(self,variable_name,trajectories):
        # time-invariant nominal scaling
        # this method works only with ipopt
        if self._discretized is False:
            raise RuntimeError('apply discretization first before runing simulation')
        
        if variable_name == 'Z':
            var = self.model.Z
            inner_set = self.model.time
        elif variable_name == 'dZdt':
            var = self.model.dZdt
            inner_set = self.model.time
        elif variable_name == 'C':
            var = self.model.C
            inner_set = self._meas_times
        elif variable_name == 'S':
            var = self.model.S
            inner_set = self._meas_lambdas
        else:
            raise RuntimeError('Initialization of variable {} is not supported'.format(variable_name))

        mixture_components = trajectories.columns

        nominal_vals = dict()
        for component in mixture_components:
            nominal_vals[component] = abs(trajectories[component].max())
            if component not in self._mixture_components:
                raise RuntimeError('Mixture component {} is not in model mixture components'.format(component))

        tol = 1e-5
        for component in mixture_components:
            if nominal_vals[component]>= tol:
                scale = 1.0/nominal_vals[component]
                for t in inner_set:
                    self.model.scaling_factor.set_value(var[t,component],scale)

        self._ipopt_scaled = True
            
    def run_sim(self,solver,tee=False,solver_opts={}):

        if self._discretized is False:
            raise RuntimeError('apply discretization first before runing simulation')

        # Look at the output in results
        #self.model.write('f.nl')
        opt = SolverFactory(solver)

        for key, val in solver_opts.iteritems():
            opt.options[key]=val

        solver_results = opt.solve(self.model,tee=tee)
        results = ResultsObject()

        Z_var = self.model.Z
        dZ_var = self.model.dZdt

        
        c_results = []
        for t in self._times:
            for k in self._mixture_components:
                c_results.append(Z_var[t,k].value)

        c_array = np.array(c_results).reshape((self._n_times,self._n_components))
        
        results.Z = pd.DataFrame(data=c_array,
                                 columns=self._mixture_components,
                                 index=self._times)

        dc_results = []
        for t in self._times:
            for k in self._mixture_components:
                dc_results.append(dZ_var[t,k].value)

        dc_array = np.array(dc_results).reshape((self._n_times,self._n_components))
        
        results.dZdt = pd.DataFrame(data=dc_array,
                                 columns=self._mixture_components,
                                 index=self._times)

        if self._spectra_given and self.model.nobjectives()==0: 

            D_data = self.model.D
            
            if self._n_meas_times and self._n_meas_times<self._n_components:
                raise RuntimeError('Not enough measurements num_meas>= num_components')

            # solves over determined system
            c_noise_array, s_array = self._solve_CS_from_D(results.Z)

            d_results = []
            for t in self._meas_times:
                for l in self._meas_lambdas:
                    d_results.append(D_data[t,l])
            d_array = np.array(d_results).reshape((self._n_meas_times,self._n_meas_lambdas))
            
            results.C = pd.DataFrame(data=c_noise_array,
                                           columns=self._mixture_components,
                                           index=self._meas_times)
            
            results.S = pd.DataFrame(data=s_array,
                                     columns=self._mixture_components,
                                     index=self._meas_lambdas)

            results.D = pd.DataFrame(data=d_array,
                                     columns=self._meas_lambdas,
                                     index=self._meas_times)

            for t in self.model.meas_times:
                for k in self._mixture_components:
                    self.model.C[t,k].value = results.C[k][t]

            for l in self.model.meas_lambdas:
                for k in self._mixture_components:
                    self.model.S[l,k].value =  results.S[k][l]
            
        else:
            c_noise_results = []
            for t in self._meas_times:
                for k in self._mixture_components:
                    c_noise_results.append(Z_var[t,k].value)
                    
            s_results = []
            for l in self._meas_lambdas:
                for k in self._mixture_components:
                    s_results.append(self.model.S[l,k].value)

            d_results = []
            if s_results and c_noise_results:
                for i,t in enumerate(self._meas_times):
                    for j,l in enumerate(self._meas_lambdas):
                        suma = 0.0
                        for w,k in enumerate(self._mixture_components):
                            C = c_noise_results[i*self._n_components+w]
                            S = s_results[j*self._n_components+w]
                            suma+= C*S
                        d_results.append(suma)
                    
            c_noise_array = np.array(c_noise_results).reshape((self._n_meas_times,self._n_components))
            s_array = np.array(s_results).reshape((self._n_meas_lambdas,self._n_components))
            d_array = np.array(d_results).reshape((self._n_meas_times,self._n_meas_lambdas))
            
            results.C = pd.DataFrame(data=c_noise_array,
                                           columns=self._mixture_components,
                                           index=self._meas_times)
            results.S = pd.DataFrame(data=s_array,
                                     columns=self._mixture_components,
                                     index=self._meas_lambdas)
            
                        
            d_array = np.array(d_results).reshape((self._n_meas_times,self._n_meas_lambdas))
            results.D = pd.DataFrame(data=d_array,
                                     columns=self._meas_lambdas,
                                     index=self._meas_times)
            
        param_vals = dict()
        for name in self.model.parameter_names:
            param_vals[name] = self.model.P[name].value

        results.P = param_vals
        return results
        


