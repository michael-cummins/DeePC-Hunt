from .utils import block_hankel, block_hankel_torch
import torch
import torch.nn as nn
from torch.nn.parameter import Parameter
from cvxpylayers.torch import CvxpyLayer
import numpy as np
import cvxpy as cp
import time

class DeePC(nn.Module):

    """
    Differentiable DeePC Module
    """

    def __init__(self, ud: np.array, yd: np.array, y_constraints: np.array, u_constraints: np.array, 
                 N: int, Tini: int, p: int, m: int, device : str,
                 stochastic_y=False, stochastic_u=False, linear=True, n_batch=1,
                 q=None, r=None, lam_y=None, lam_g1=None, lam_g2=None, lam_u=None):
        super().__init__()

        """
        Initialise differentiable DeePC
        args:
            - ud : time series vector of input signals - always pass as shape (T, m)
            - yd : time series vector of output signals 
            - y_constraints : State-wise Constraints on output signal
            - u_constraints : State-wise Constraints on input signal
            - N : Future Time horizon
            - Tini : Initial time horizon
            - T : Length of data
            - p : Dimension of output signal
            - m : Dimension of input signal

            - stochastic : Set true if noise if output signals contain noise
            - linear : Set true if input and putput signals are collected from a linear system

            - q : vector of diagonal elemetns of Q,
                if passed as none -> randomly initialise as torch parameter in R^p
            - r : vector of diagonal elemetns of R,
                if passed as none -> randomly initialise as torch parameter in R^m
            - lam_y : regularization paramter for sig_y 
                    -> if left as none, randomly initialise as torch parameter 
            - lam_g1 : regularization paramter for sum_squares regularization on g 
                    -> if left as none, randomly initialise as torch parameter 
            - lam_g2 : regularization paramter for norm1 regularization on g 
                    -> if left as none, randomly initialise as torch parameter 
        """
        
        self.T = int(len(ud))
        self.ud = ud
        self.yd = yd
        self.Tini = Tini
        self.N = N
        self.p = p
        self.m = m
        self.y_constraints = y_constraints
        self.u_constraints = u_constraints
        self.stochastic_y = stochastic_y
        self.stochastic_u = stochastic_u
        self.device = device # TODO: Shouldn't have to do this
        self.linear = linear
        self.n_batch = n_batch
        self.lam_g1 = lam_g1
        self.lam_g2 = lam_g2
        self.lam_u = lam_u
        self.lam_y = lam_y

        # Initialise torch parameters
        if isinstance(q, torch.Tensor):
            self.q = q.to(self.device)
        else: 
            self.q = Parameter(torch.randn(size=(self.p,))*0.01 + 100)
        
        if isinstance(r, torch.Tensor):
            self.r = r.to(self.device)
        else : 
            self.r = Parameter(torch.randn(size=(self.m,))*0.001 + 0.01)

        if stochastic_y:
            if isinstance(lam_y, torch.Tensor):
                self.lam_y = lam_y 
            else:
                self.lam_y = Parameter(torch.randn((1,))*0.001 + 200)
       
        if stochastic_u:
            if isinstance(lam_u, torch.Tensor):
                self.lam_u = lam_u 
            else:
                self.lam_u = Parameter(torch.randn((1,))*0.01 + 200)

        if not linear:
            if isinstance(lam_g1, torch.Tensor):
                self.lam_g1 = lam_g1
            else:
                self.lam_g1 = Parameter(torch.randn((1,))*0.0001 + 200)
            if isinstance(lam_g2, torch.Tensor):
                self.lam_g2 = lam_g2
            else:
                self.lam_g2 = Parameter(torch.randn((1,))*0.001 + 200)

        # Check for full row rank
        H = block_hankel(w=ud.reshape((m*self.T,)), L=Tini+N+p, d=m)
        rank = np.linalg.matrix_rank(H)
        if rank != H.shape[0]:
            raise ValueError('Data is not persistently exciting')
        
        # Construct data matrices
        U = block_hankel(w=ud.reshape((m*self.T,)), L=Tini+N, d=m)
        Y = block_hankel(w=yd.reshape((p*self.T,)), L=Tini+N, d=p)
        self.Up = U[0:m*Tini,:]
        self.Yp = Y[0:p*Tini,:]
        self.Uf = U[Tini*m:,:]
        self.Yf = Y[Tini*p:,:]

        # Initialise Optimisation variables
        g = cp.Variable(self.T-self.Tini-self.N+1)
        self.y = cp.Variable(N*p)
        e = cp.Variable(N*p)
        self.u = cp.Variable(N*m)
        sig_y = cp.Variable(self.Tini*self.p) 
        sig_u = cp.Variable(self.Tini*self.m) 

        # Constant for sum_squares regularization on G
        PI = np.vstack([self.Up, self.Yp, self.Uf])
        PI = np.linalg.pinv(PI)@PI
        I = np.eye(PI.shape[0])

        # Initalise optimization parameters and cost
        l_g1, l_g2 = cp.Parameter(shape=(1,), nonneg=True), cp.Parameter(shape=(1,), nonneg=True)
        l_y = cp.Parameter(shape=(1,), nonneg=True)
        l_u = cp.Parameter(shape=(1,), nonneg=True)
        Q_block_sqrt, R_block_sqrt = cp.Parameter((p*N,p*N)), cp.Parameter((m*N,m*N))
        ref = cp.Parameter((N*p,))
        
        u_ini, y_ini = cp.Parameter(Tini*m), cp.Parameter(Tini*p)
        cost = cp.sum_squares(cp.psd_wrap(Q_block_sqrt) @ e) + cp.sum_squares(cp.psd_wrap(R_block_sqrt) @ self.u)
        assert cost.is_dpp()

        # Set constraints and cost function according to system (nonlinear / stochastic)
        if not linear:
            cost += cp.sum_squares((I - PI)@g)*l_g1 + cp.norm1(g)*l_g2 
            assert cost.is_dpp()

        cost += cp.norm1(sig_y)*l_y if self.stochastic_y else 0
        cost += cp.norm1(sig_u)*l_u if self.stochastic_u else 0
        assert cost.is_dpp()

        constraints = [
            e == self.y - ref,  # necessary for paramaterized programming
            self.Uf@g == self.u,
            self.Yf@g == self.y,
            cp.abs(self.u) <= self.u_constraints,
            cp.abs(self.y) <= self.y_constraints,
            self.y[-self.p:] == ref[-self.p:]
        ]
        constraints.append(self.Up@g == u_ini + sig_u) if self.stochastic_u else constraints.append(self.Up@g == u_ini)
        constraints.append(self.Yp@g == y_ini + sig_y) if self.stochastic_y else constraints.append(self.Yp@g == y_ini)

        # Initialise optimization problem
        problem = cp.Problem(cp.Minimize(cost), constraints)
        assert problem.is_dcp()
        assert problem.is_dpp()

        variables = [g, e, self.u, self.y]
        params = [Q_block_sqrt, R_block_sqrt, u_ini, y_ini, ref]
        
        if not linear:
            params.append(l_g1)
            params.append(l_g2)
        
        if stochastic_y:
            variables.append(sig_y)
            params.append(l_y)
        
        if stochastic_u:
            variables.append(sig_u)
            params.append(l_u)

        self.QP_layer = CvxpyLayer(problem=problem, parameters=params, variables=variables)
    
    def forward(self, ref: torch.Tensor, uref: torch.Tensor, u_ini: torch.Tensor, y_ini: torch.Tensor) -> list[torch.Tensor]:

        """
        Forward call
        args :
            - ref : Reference trajectory 
            - u_ini : Initial input signal
            - y_ini : Initial Output signal

        Returns : 
            input : optimal input signal
            output : optimal output signal
            cost : optimal cost
        """
        if uref == None: uref = torch.zeros(self.N*self.m).repeat(self.n_batch, 1).to(self.device)
        if ref == None: ref = torch.zeros(self.N*self.p).repeat(self.n_batch, 1).to(self.device)

        # Construct Q and R matrices 
        if u_ini.ndim > 1 or y_ini.ndim > 1 or ref.ndim > 1:
            Q = torch.diag(torch.kron(torch.ones(self.N).to(self.device), torch.sqrt(self.q))).repeat(self.n_batch, 1, 1).to(self.device)
            R = torch.diag(torch.kron(torch.ones(self.N).to(self.device), torch.sqrt(self.r))).repeat(self.n_batch, 1, 1).to(self.device)
        else :
            Q = torch.diag(torch.kron(torch.ones(self.N).to(self.device), torch.sqrt(self.q))).to(self.device)
            R = torch.diag(torch.kron(torch.ones(self.N).to(self.device), torch.sqrt(self.r))).to(self.device)

        params = [Q, R, u_ini, y_ini, ref]
        
        # Add paramters and system
        if not self.linear:
            params.append(self.lam_g1)
            params.append(self.lam_g2.repeat(self.n_batch,1))
        if self.stochastic_y:
            params.append(self.lam_y.repeat(self.n_batch,1))
        if self.stochastic_u:
            params.append(self.lam_u.repeat(self.n_batch,1))

        out = self.QP_layer(*params, solver_args={"solve_method": "SCS"})
        g, input, output = out[0], out[2], out[3]
        vars = [g, input, output]
        
        if self.stochastic_y : vars.append(out[-2])
        if self.stochastic_u : vars.append(out[-1])

        return vars

    def get_PI(self):
        # Constant for sum_squares regularization on g
        PI = np.vstack([self.Up, self.Yp, self.Uf])
        PI = np.linalg.pinv(PI)@PI
        I = np.eye(PI.shape[0])
        return I, PI

    def initialise(self, lam_y=None, lam_u=None, lam_g1=None, lam_g2=None):
        if self.lam_g1 is not None:
            self.lam_g1.data = torch.Tensor([lam_g1])
        if self.lam_g2 is not None:
            self.lam_g2.data = torch.Tensor([lam_g2])
        if self.lam_y is not None:
            self.lam_y.data = torch.Tensor([lam_y])
        if self.lam_u is not None:
            self.lam_u.data = torch.Tensor([lam_u])