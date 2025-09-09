# DeePC-Hunt
### Data-enabled predictive control hyperparameter tuning via differentiable optimization layers

DeePC-Hunt is a method for optimising over the hyperparameters of DeePC using [analytical policy gradients](https://arxiv.org/abs/2202.00817) and [differentiable optimization layers](https://locuslab.github.io/2019-10-28-cvxpylayers/). This method has been developed as part of my bachelor thesis, carried out at the [Automatic Control Laboratory (IfA)](https://control.ee.ethz.ch/). Supervised by [Alberto Padoan](https://www.albertopadoan.com/), [Keith Moffat](https://www.keithmoffat.com/) and [Florian Dorfler](http://people.ee.ethz.ch/~floriand/). A pre-print is available on [arxiv](https://arxiv.org/abs/2412.06481).

Developed in a conda environment on Ubuntu 22.04 with Python 3.10. 

Differentiable DeePC layer is inspired by [Differentiable MPC](https://github.com/locuslab/differentiable-mpc) and built using [CvxpyLayers](https://github.com/cvxgrp/cvxpylayers).

## Installation
Clone the repo and install from source
```
cd DeePC-Hunt && pip install -e .
```
Extra packages necessary for running the example notebooks are in examples/requirements.txt if needed.
```
pip install -r examples/requirements.txt
```

DeePC-Hunt has the following dependencies.
* Python3
* [PyTorch](https://pytorch.org/) >= 1.0
* [CvxpyLayers](https://github.com/cvxgrp/cvxpylayers) >= 1.0

## Usage
Data-enabled Predictive Control ([DeePC](https://arxiv.org/abs/1811.05890)) is a data-driven non-parametric algorithm for combined identification (learning) and control of dynamical systems. It leverages the solution of the following optimization problem in a receding horizon fashion.

![Problem Formulation](https://github.com/michael-cummins/DeePC-Hunt/blob/main/videos/DeePC.png)

DeePC can achieve performance that rivals MPC on non-linear and stochastic systems ([see here](https://arxiv.org/abs/2101.01273)) but is highly sensitive to the choice of regularization parameters $\theta_i$. DeePC-Hunt addresses this problem by automatically tuning these parameters. The performance of DeePC-Hunt has been validated on a [rocket lander](https://github.com/michael-cummins/DeePC-Hunt/examples/rocket.ipynb) modelling the falcon 9 and a [LTI](https://github.com/michael-cummins/DeePC-Hunt/examples/linear_deepc.ipynb) system. To run these example notebooks, you can clone this directory and open it in a VS-Code environment with the Jupyter Notebook extension

### Rocket - before training

https://github.com/michael-cummins/DeePC-Hunt/assets/72135336/eacd384e-b69d-428e-aa3e-1b4e669a3485




### Rocket - after training (episode 70)

After running DeePC-Hunt for 70 episodes, the controller now stabilizes the system.




https://github.com/michael-cummins/DeePC-Hunt/assets/72135336/b88aedf8-b816-4a89-a9ef-3bfa9b9c9d0b

## Citing

If you use DeePC-Hunt in your research or found the ideas useful, please cite the [paper](https://arxiv.org/abs/2412.06481)

```
@article{cummins2025deepc,
  title={DeePC-Hunt: Data-enabled Predictive Control Hyperparameter Tuning via Differentiable Optimization},
  author={Cummins, Michael and Padoan, Alberto and Moffat, Keith and D{\"o}rfler, Florian and Lygeros, John},
  journal={Proceedings of Machine Learning Research vol},
  volume={283},
  pages={1--13},
  year={2025}
}
```

