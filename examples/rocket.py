import torch.nn as nn
from numpy import genfromtxt
import numpy as np
import torch
from deepc_hunt.dynamics import CartpoleDx, RocketDx
from deepc_hunt import DeePC, Trainer
from deepc_hunt.controllers import npDeePC, npMPC
from deepc_hunt.utils import tensor2np
import pickle
import matplotlib.pyplot as plt
import gymnasium as gym
from tqdm import tqdm
import coco_rocket_lander  # need to import to call gym.make()
from coco_rocket_lander.env import SystemModel

if __name__ == '__main__':

    q = torch.Tensor([100,10,5,1,3000,30]) # 6-tuple (x, y, x_dot, y_dot, theta, theta_dot)
    r = torch.Tensor([0.01,0.01,0.01]) # 3-tuple (F_E, F_S, phi)
    q_np = tensor2np(q)
    r_np = tensor2np(r)

    n = 6 # states
    m = 3 # inputs
    p = 6 # outputs

    Tini = 1 # number of past measurements (also called T_ini)
    Tf = 10 # number of future measurements (also called K)
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    n_batch = 1

    ud = np.genfromtxt('data/rocket_ud.csv', delimiter=',')
    yd = np.genfromtxt('data/rocket_yd.csv', delimiter=',')

    # y_constraints = np.ones(Tf*p)*1e5 #Unconstrained
    # u_constraints = np.ones(Tf*m)
    y_upper = np.kron(np.ones(Tf), np.array([33,26.6,100,100,0.6,100]))
    y_lower = np.kron(np.ones(Tf), np.array([0,7,-100,-100,-0.6,-100]))
    u_upper = np.kron(np.ones(Tf), np.array([1,1,1]))
    u_lower = np.kron(np.ones(Tf), np.array([0,-1,-1]))
    y_constraints = (y_lower, y_upper)
    u_constraints = (u_lower, u_upper)

    """ 
    Define Policies 
    """

    # DeePC Policies
    params = {
        'deepc_good': (49.837, 8.364, 1000.05), 
        'deepc_bad': (27.475, 2.128, 946.06), 
        'deepc_untrained': (50, 50, 1000)
    }

    deepc_policies = {
        k: npDeePC(
            ud=ud, yd=yd, u_constraints=u_constraints, y_constraints=y_constraints,
            Tini=Tini, N=Tf, m=m, p=p, n=n
        ).setup(Q=np.diag(q_np), R=np.diag(r_np),lam_g1=l1,lam_g2=l2,lam_y=ly)
        for k, (l1, l2, ly) in params.items()
    }
    
    # MPC Policies
    x_eq = np.array([16.6,7.47,0,0,0,0]) # Landing position
    u_eq = np.array([0,0,0])
    rocket_good = RocketDx(true_model=True)
    A_good, B_good = rocket_good.linearise(x_eq=x_eq, u_eq=u_eq, discrete=True)
    rocket_bad = RocketDx(true_model=False)
    A_bad, B_bad = rocket_bad.linearise(x_eq=x_eq, u_eq=u_eq, discrete=True)
    matrices = {'mpc_good':(A_good, B_good), 'mpc_bad':(A_bad, B_bad)}
    mpc_policies = {
        k: npMPC(
            A=A, B=B, Q=np.diag(q_np), R=np.diag(r_np), N=Tf, 
            u_constraints=u_constraints, y_constraints=y_constraints
        ).setup() for k, (A, B) in matrices.items()
    }

    policies = {**mpc_policies, **deepc_policies}
    # policies = deepc_policies

    """ 
    Run simulations for cost and success rate
    """
    
    samples = 50
    costs = {}
    successful = {}
    seeds = np.uint8(np.random.uniform(low=1,high=99,size=(samples,)))

    for name, policy in policies.items():
        pbar = tqdm(range(samples))
        pbar.set_description(name)
        costs[name] = []
        successful[name] = []
        
        for i in pbar:
            costs[name].append(0)

            # Start Simulator
            np.random.seed(seeds[i])
            initial_position = (
                    np.random.uniform(low=0.1,high=0.9), 
                    np.random.uniform(low=0.7, high=0.9), 
                    np.random.uniform(low=-0.15, high=0.15)
                )
            args = {"initial_position": initial_position}
            env = gym.make(
                "coco_rocket_lander/RocketLander-v0", 
                render_mode="rgb_array", args=args
            )
            obs,info = env.reset() 

            # Initial state for DeePC
            u_past_sim = np.zeros(3*Tini)
            y_past_sim = np.tile(obs[0:6],Tini)

            landing_position = env.get_landing_position()  # (x, y, theta) in [m, m, radians]
            deepc_reference = [0,0,0,0,0,0]
            deepc_reference[0] = landing_position[0]
            deepc_reference[1] = landing_position[1] 
            deepc_reference = np.tile(deepc_reference,Tf)
            uref = np.zeros(m*Tf)
            stop_u = np.array([0,0,0])
            Q = np.sqrt(np.diag(q_np))
            R = np.sqrt(np.diag(r_np))
            
            touched_ground = False
            done = False
            
            while not done:
                
                # Get control action
                if((obs[6] and obs[7])): # if both sensors touch the ground, stop
                    action = stop_u
                    # print(action)
                    # touched_ground = True
                else:
                    # action = stop_u
                    try:
                        action, _ = policy.solve(
                            y_ref=deepc_reference, u_ref=uref,
                            y_ini=y_past_sim[-p:],
                            u_ini=u_past_sim,
                        )
                    except: break
                
                # store input & output for DeePC
                u_past_sim = np.append(u_past_sim[3:], action)
                y_past_sim = np.append(y_past_sim, obs[0:6])
                next_obs, rewards, done, _, info = env.step(action)
                obs = next_obs
                costs[name][i] += np.linalg.norm(Q@(obs[:6]-deepc_reference[:6])) + np.linalg.norm(R@(action-uref[:3]))

            # print(f'obs:{obs}')
            if obs[6] and obs[7] and obs[1]>=landing_position[1]: successful[name].append(1)
            else: successful[name].append(0)
            
            with open('success_dict.pkl', 'wb') as f:
                pickle.dump(successful, f)
            with open('costs_dict.pkl', 'wb') as f:
                pickle.dump(costs, f)

    # print(f'Landing pos: {landing_position}')
    print(successful)
    print(costs)


    # with open('success_dict.pkl', 'rb') as f:
    #     successful = pickle.load(f)
    # with open('costs_dict.pkl', 'rb') as f:
    #     costs = pickle.load(f)
    # print(successful)
    # print(costs)