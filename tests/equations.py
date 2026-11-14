"""Equations people actually write: classical physics, quantum physics, and machine learning.

Each item is ``(name, tex)``. The tests draw every one, and check that every
ledger row can be found again in the typeset formula.
"""

PHYSICS = [
    ("newton", r"\vec{F}=m\vec{a}"),
    ("gravitation", r"F=G\frac{m_1 m_2}{r^2}"),
    ("kinetic energy", r"E_k=\frac{1}{2}mv^2"),
    ("euler-lagrange", r"\frac{d}{dt}\frac{\partial L}{\partial \dot{q}}-\frac{\partial L}{\partial q}=0"),
    ("gauss", r"\nabla\cdot\vec{E}=\frac{\rho}{\varepsilon_0}"),
    ("ampere-maxwell", r"\nabla\times\vec{B}=\mu_0\vec{J}+\mu_0\varepsilon_0\frac{\partial\vec{E}}{\partial t}"),
    ("wave", r"\frac{\partial^2 u}{\partial t^2}=c^2\nabla^2 u"),
    ("lorentz factor", r"\gamma=\frac{1}{\sqrt{1-v^2/c^2}}"),
    ("energy-momentum", r"E^2=(pc)^2+(mc^2)^2"),
    ("einstein field", r"G_{\mu\nu}+\Lambda g_{\mu\nu}=\frac{8\pi G}{c^4}T_{\mu\nu}"),
    ("boltzmann entropy", r"S=k_B\ln\Omega"),
    ("ideal gas", r"PV=nRT"),
    ("navier-stokes", r"\rho\left(\frac{\partial\vec{u}}{\partial t}+\vec{u}\cdot\nabla\vec{u}\right)=-\nabla p+\mu\nabla^2\vec{u}"),
    ("heat", r"\frac{\partial T}{\partial t}=\alpha\nabla^2 T"),
    ("planck law", r"B_\nu(T)=\frac{2h\nu^3}{c^2}\frac{1}{e^{h\nu/k_BT}-1}"),
    ("fourier transform", r"\psi(x)=\int_{-\infty}^{\infty}\hat{\psi}(\xi)\,e^{2\pi i x \xi}\,d\xi"),
    ("gaussian", r"f(x)=\frac{1}{\sigma\sqrt{2\pi}}\exp\left(-\frac{(x-\mu)^{2}}{2\sigma^{2}}\right)"),
    ("stokes theorem", r"\oint_{\partial S}\vec{F}\cdot d\vec{r}=\iint_S(\nabla\times\vec{F})\cdot d\vec{A}"),
]

QUANTUM = [
    ("schrodinger", r"i\hbar\frac{\partial}{\partial t}\Psi=\hat{H}\Psi"),
    ("stationary schrodinger", r"-\frac{\hbar^2}{2m}\nabla^2\psi+V\psi=E\psi"),
    ("uncertainty", r"\Delta x\,\Delta p\geq\frac{\hbar}{2}"),
    ("commutator", r"[\hat{x},\hat{p}]=i\hbar"),
    ("born rule", r"P(x)=|\psi(x)|^2"),
    ("expectation", r"\langle A\rangle=\langle\psi|\hat{A}|\psi\rangle"),
    ("dirac", r"(i\gamma^\mu\partial_\mu-m)\psi=0"),
    ("de broglie", r"\lambda=\frac{h}{p}"),
    ("unitary", r"U^\dagger U=I"),
    ("density matrix", r"\rho=\sum_i p_i|\psi_i\rangle\langle\psi_i|"),
    ("von neumann entropy", r"S=-\mathrm{Tr}(\rho\ln\rho)"),
    ("bell state", r"|\Phi^+\rangle=\frac{1}{\sqrt{2}}(|00\rangle+|11\rangle)"),
    ("path integral", r"Z=\int\mathcal{D}\phi\,e^{iS[\phi]/\hbar}"),
    ("oscillator levels", r"E_n=\hbar\omega\left(n+\frac{1}{2}\right)"),
    ("ladder operator", r"\hat{a}^\dagger|n\rangle=\sqrt{n+1}\,|n+1\rangle"),
    ("heisenberg picture", r"\frac{d\hat{A}}{dt}=\frac{i}{\hbar}[\hat{H},\hat{A}]"),
]

ML = [
    ("softmax", r"\sigma(z)_i=\frac{e^{z_i}}{\sum_{j=1}^{K}e^{z_j}}"),
    ("cross entropy", r"L=-\sum_{i}y_i\log\hat{y}_i"),
    ("gradient descent", r"\theta_{t+1}=\theta_t-\eta\nabla_\theta L(\theta_t)"),
    ("attention", r"\mathrm{Attn}(Q,K,V)=\mathrm{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V"),
    ("kl divergence", r"D_{KL}(P\|Q)=\sum_x P(x)\log\frac{P(x)}{Q(x)}"),
    ("elbo", r"\log p(x)\geq\mathbb{E}_{q(z|x)}[\log p(x|z)]-D_{KL}(q(z|x)\|p(z))"),
    ("diffusion forward", r"x_t=\sqrt{\bar{\alpha}_t}\,x_0+\sqrt{1-\bar{\alpha}_t}\,\epsilon"),
    ("flow matching", r"L=\mathbb{E}\|v_\theta(x_t,t)-(\epsilon-x_0)\|^2"),
    ("bayes", r"P(A|B)=\frac{P(B|A)P(A)}{P(B)}"),
    ("adam moment", r"\hat{m}_t=\frac{m_t}{1-\beta_1^t}"),
    ("layer norm", r"y=\frac{x-\mu}{\sqrt{\sigma^2+\epsilon}}\gamma+\beta"),
    ("ridge regression", r"w^*=(X^TX+\lambda I)^{-1}X^Ty"),
    ("svd", r"A=U\Sigma V^\top"),
    ("bellman", r"Q^*(s,a)=r+\gamma\max_{a'}Q^*(s',a')"),
    ("lora", r"W=W_0+\frac{\alpha}{r}BA"),
    ("sigmoid", r"\sigma(x)=\frac{1}{1+e^{-x}}"),
    ("gan", r"\min_G\max_D\mathbb{E}_x[\log D(x)]+\mathbb{E}_z[\log(1-D(G(z)))]"),
    ("procrustes", r"A=VU^\top,\qquad Z^\top X=U\,\Sigma\,V^\top"),
    ("asymmetric target", r"u^\star=P\,\epsilon-x_0,\qquad P=A_eA_e^\top"),
]

ALL = PHYSICS + QUANTUM + ML
