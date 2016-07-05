from pyomo.environ import *
from pyomo.dae import *
from kipet.sim.PyomoSimulator import *
import copy
import os

class VarianceEstimator(PyomoSimulator):
    def __init__(self,model):
        super(VarianceEstimator, self).__init__(model)

        self.S_model = ConcreteModel()
        self.S_model.S = Var(self._meas_lambdas,
                             self._mixture_components,
                             bounds=(0.0,None),
                             initialize=1.0)

        self.C_model = ConcreteModel()
        self.C_model.C = Var(self._meas_times,
                           self._mixture_components,
                           bounds=(0.0,None),
                           initialize=1.0)

        # To pass scaling to the submodels
        self.C_model.scaling_factor = Suffix(direction=Suffix.EXPORT)
        self.S_model.scaling_factor = Suffix(direction=Suffix.EXPORT)

        self._tmp1 = "tmp_init"
        self._tmp2 = "tmp_solve_Z"
        self._tmp3 = "tmp_solve_S"
        self._tmp4 = "tmp_solve_C"

    def __del__(self):
        os.remove(self._tmp1)
        os.remove(self._tmp2)
        os.remove(self._tmp3)
        os.remove(self._tmp4)
        
    def run_sim(self,solver,tee=False,solver_opts={}):
        raise NotImplementedError("VarianceEstimator object does not have run_sim method. Call run_opt")

    def initialize_from_trajectory(self,variable_name,trajectories):
        super(VarianceEstimator, self).initialize_from_trajectory(variable_name,trajectories)
        if variable_name=='S':
            for k,v in self.model.S.iteritems():
                self.S_model.S[k].value = v.value
        if variable_name=='C':
            for k,v in self.model.C.iteritems():
                self.C_model.C[k].value = v.value        

    def scale_variables_from_trajectory(self,variable_name,trajectories):
        super(VarianceEstimator, self).scale_variables_from_trajectory(variable_name,trajectories)
        if variable_name=='S':
            for k,v in self.model.S.iteritems():
                value = self.model.scaling_factor.get(self.model.S[k])
                self.S_model.scaling_factor.set_value(v,value) 
        if variable_name=='C':
            for k,v in self.model.C.iteritems():
                value = self.model.scaling_factor.get(self.model.C[k])
                self.C_model.scaling_factor.set_value(v,value) 
        

    def _solve_initalization(self,
                             optimizer,
                             subset_lambdas=None):

        if subset_lambdas:
            set_A = set(subset_lambdas)
        else:
            set_A = self._meas_lambdas

        # build model
        dae = self.model
        m = ConcreteModel()
        m.A = Set(initialize=set_A)
        m.add_component('dae', dae)
        
        # build objective
        obj = 0.0
        for t in self._meas_times:
            for l in m.A:
                D_bar = sum(m.dae.Z[t,k]*m.dae.S[l,k] for k in m.dae.mixture_components)
                obj+= (m.dae.D[t,l] - D_bar)**2
        m.objective = Objective(expr=obj)

        solver_results = optimizer.solve(m,logfile=self._tmp1)

        for t in self._meas_times:
            for k in self._mixture_components:
                m.dae.C[t,k].value = m.dae.Z[t,k].value
                self.C_model.C[t,k].value =  m.dae.C[t,k].value
        m.del_component('dae')

    def _solve_Z(self,
                 optimizer,
                 C_trajectory=None):
        
        dae = self.model
        m = ConcreteModel()
        m.add_component('dae', dae)
        
        obj = 0.0
        reciprocal_ntp = 1.0/len(m.dae.time)
        if C_trajectory is not None:
            for k in m.dae.mixture_components:
                x = sum((C_trajectory[k][t]-m.dae.Z[t,k])**2 for t in self._meas_times)
                #x*= reciprocal_ntp
                obj+= x
        else:
            # asume this value was computed beforehand
            for t in self._meas_times:
                for k in self._mixture_components:
                    m.dae.C[t,k].fixed = True
            
            for k in m.dae.mixture_components:
                x = sum((m.dae.C[t,k]-m.dae.Z[t,k])**2 for t in self._meas_times)
                #x*= reciprocal_ntp
                obj+= x

        m.objective = Objective(expr=obj)

        solver_results = optimizer.solve(m,logfile=self._tmp2)

        if C_trajectory is not None:
            # unfixes all concentrations
            for t in self._meas_times:
                for k in self._mixture_components:
                    m.dae.C[t,k].fixed = False
        
        m.del_component('dae')

    def _solve_S(self,
                 optimizer,
                 Z_trajectory=None):
        
        obj = 0.0
        if Z_trajectory is not None:
            for t in self._meas_times:
                for l in self._meas_lambdas:
                    D_bar = sum(self.S_model.S[l,k]*Z_trajectory[k][t] for k in self._mixture_components)
                    obj+=(self.model.D[t,l]-D_bar)**2
        else:
            # asumes base model has been solved already for Z
            for t in self._meas_times:
                for l in self._meas_lambdas:
                    D_bar = sum(self.S_model.S[l,k]*self.model.Z[t,k].value for k in self._mixture_components)
                    obj+=(self.model.D[t,l]-D_bar)**2
                    
        self.S_model.objective = Objective(expr=obj)

        solver_results = optimizer.solve(self.S_model,logfile=self._tmp3)
        self.S_model.del_component('objective')
        
        #updates values in main model
        for k,v in self.S_model.S.iteritems():
            self.model.S[k].value = v.value
        
    def _solve_C(self,
                 optimizer,
                 S_trajectory=None):

        
        obj = 0.0
        if S_trajectory is not None:
            for t in self._meas_times:
                for l in self._meas_lambdas:
                    D_bar = sum(S_trajectory[k][l]*self.C_model.C[t,k] for k in self._mixture_components)
                    obj+=(self.model.D[t,l]-D_bar)**2
        else:
            # asumes that s model has been solved first
            for t in self._meas_times:
                for l in self._meas_lambdas:
                    D_bar = sum(self.S_model.S[l,k].value*self.C_model.C[t,k] for k in self._mixture_components)
                    obj+=(self.model.D[t,l]-D_bar)**2
                    
        self.C_model.objective = Objective(expr=obj)

        solver_results = optimizer.solve(self.C_model,logfile=self._tmp4)
        self.C_model.del_component('objective')

        for t in self._meas_times:
            for k in self._mixture_components:
                self.model.C[t,k].value = self.C_model.C[t,k].value

    def _solve_variances(self,S_trajectory,Z_trajectory):
        nl = self._n_meas_lambdas
        nt = self._n_meas_times
        nc = self._n_components
        A = np.ones((nl,nc+1))
        b = np.zeros((nl,1))

        reciprocal_nt = 1.0/nt
        for i,l in enumerate(self._meas_lambdas):
            for j,t in enumerate(self._meas_times):
                D_bar = 0.0
                for w,k in enumerate(self._mixture_components):
                    A[i,w] = S_trajectory[k][l]**2
                    D_bar += S_trajectory[k][l]*Z_trajectory[k][t]
                b[i] += (self.model.D[t,l]-D_bar)**2
            b[i]*=reciprocal_nt

        results = np.linalg.lstsq(A, b)
        return results            

    def _log_iterations(self,filename,iteration):
        f = open(filename, "a")

        f.write("\n#######################Iteration {}#######################\n".format(iteration))
        if iteration==0:
            tf = open(self._tmp1,'r')
            f.write("\n#######################Initialization#######################\n")
            f.write(tf.read())
            tf.close()
        tf = open(self._tmp2,'r')
        f.write("\n#######################Solve Z#######################\n")
        f.write(tf.read())
        tf.close()
        tf = open(self._tmp3,'r')
        f.write("\n#######################Solve S#######################\n")
        f.write(tf.read())
        tf.close()

        tf = open(self._tmp4,'r')
        f.write("\n#######################Solve C#######################\n")
        f.write(tf.read())
        
        f.close()
    
    def run_opt(self,solver,tee=False,solver_opts={},variances={}):
        
        Z_var = self.model.Z 
        dZ_var = self.model.dZdt

        if self._discretized is False:
            raise RuntimeError('apply discretization first before runing simulation')

        # disable objectives of dae
        objectives_map = self.model.component_map(ctype=Objective,active=True)
        for obj in objectives_map.itervalues():
            obj.deactivate()

         
        opt = SolverFactory(solver)
        for key, val in solver_opts.iteritems():
            opt.options[key]=val

        print("Solving Variance estimation")
        # solves formulation 18
        self._solve_initalization(opt)
        Z_i = np.array([v.value for v in self.model.Z.itervalues()])

        # perfoms the fisrt iteration 
        self._solve_Z(opt)
        self._solve_S(opt)
        self._solve_C(opt)

        if tee:
            self._log_iterations("iterations.log",0)
        
        Z_i1 = np.array([v.value for v in self.model.Z.itervalues()])

        # starts iterating
        max_iter = 100
        tol = 5e-10
        norm_order = None
        diff = Z_i1-Z_i
        norm_diff = np.linalg.norm(diff,norm_order)

        print("{: >11} {: >16}".format('Iter','|Zi-Zi+1|'))
        print("{: >10} {: >20}".format(0,norm_diff))
        count=1
        while norm_diff>tol and count<max_iter:
            Z_i = np.array([v.value for v in self.model.Z.itervalues()])
            self._solve_Z(opt)
            Z_i1 = np.array([v.value for v in self.model.Z.itervalues()])
            norm_diff = np.linalg.norm(Z_i1-Z_i,norm_order)
            self._solve_S(opt)
            self._solve_C(opt)
            print("{: >10} {: >20}".format(count,norm_diff))
            if tee:
                self._log_iterations("iterations.log",count)
            count+=1

        results =  ResultsObject()
        results.load_from_pyomo_model(self.model,
                                      to_load=['Z','dZdt','X','dXdt','C','S'])

        res_lsq = self._solve_variances(results.S,results.Z)
        variance_dict = dict()
        for i,k in enumerate(self._mixture_components):
            variance_dict[k] = res_lsq[0][i][0]

        variance_dict['device'] = res_lsq[0][-1][0]
        results.sigma_sq = variance_dict 
        param_vals = dict()
        for name in self.model.parameter_names:
            param_vals[name] = self.model.P[name].value

        results.P = param_vals
        
        return results

            
            