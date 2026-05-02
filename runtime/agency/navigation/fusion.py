"""GODSKILL Nav v11 — Tier 5: Sensor Fusion (EKF + UKF + PF)."""
from __future__ import annotations
import math, random
from dataclasses import dataclass, field
from typing import Iterable, Optional, List
from .types import Confidence, Estimate, Pose, Position, Velocity

# ── Pure-Python matrix helpers ────────────────────────────────────────────────
Mat = List[List[float]]
Vec = List[float]

def _zeros(r,c): return [[0.0]*c for _ in range(r)]
def _eye(n):
    m=_zeros(n,n);
    for i in range(n): m[i][i]=1.0
    return m
def _mul(A,B):
    nr,nk,nc=len(A),len(B),len(B[0]); C=_zeros(nr,nc)
    for i in range(nr):
        for k in range(nk):
            if A[i][k]==0: continue
            for j in range(nc): C[i][j]+=A[i][k]*B[k][j]
    return C
def _add(A,B): return [[A[i][j]+B[i][j] for j in range(len(A[0]))] for i in range(len(A))]
def _sub(A,B): return [[A[i][j]-B[i][j] for j in range(len(A[0]))] for i in range(len(A))]
def _T(A): return [[A[j][i] for j in range(len(A))] for i in range(len(A[0]))]
def _scale(A,s): return [[A[i][j]*s for j in range(len(A[0]))] for i in range(len(A))]
def _inv2(M):
    a,b=M[0]; c,d=M[1]; det=a*d-b*c
    if abs(det)<1e-12: return [[1.0,0.0],[0.0,1.0]]
    return [[d/det,-b/det],[-c/det,a/det]]
def _chol(A):
    """Cholesky decomp, returns L s.t. A=LLᵀ (or approx if not PD)."""
    n=len(A); L=_zeros(n,n)
    for i in range(n):
        for j in range(i+1):
            s=sum(L[i][k]*L[j][k] for k in range(j))
            if i==j:
                val=A[i][i]-s
                L[i][j]=math.sqrt(max(val,1e-10))
            else:
                L[i][j]=(A[i][j]-s)/max(L[j][j],1e-10)
    return L
def _vec_add(a,b): return [a[i]+b[i] for i in range(len(a))]
def _vec_sub(a,b): return [a[i]-b[i] for i in range(len(a))]
def _mat_vec(A,v): return [sum(A[i][j]*v[j] for j in range(len(v))) for i in range(len(A))]

# ── EKF (6-state: x,y,z,vx,vy,vz) ───────────────────────────────────────────
class EKF:
    """Extended Kalman Filter. State: [x,y,z,vx,vy,vz]."""

    def __init__(self, q: float = 1.0, r: float = 5.0) -> None:
        self.x: Vec = [0.0]*6
        self.P: Mat = [[10.0 if i==j else 0.0 for j in range(6)] for i in range(6)]
        self._q = q; self._r = r

    def predict(self, dt: float) -> None:
        # Constant velocity: x_new = x+vx*dt, y_new=y+vy*dt …
        F = _eye(6)
        for i in range(3): F[i][i+3] = dt
        Q = _zeros(6,6)
        for i in range(3):
            Q[i][i]=self._q*dt**2; Q[i+3][i+3]=self._q
        self.x = _mat_vec(F, self.x)
        self.P = _add(_mul(_mul(F,self.P),_T(F)), Q)

    def update(self, z: Vec, R: Mat) -> bool:
        """z: measurement vector (len 3 for x,y,z), R: cov matrix."""
        nz = len(z)
        H = _zeros(nz,6)
        for i in range(nz): H[i][i] = 1.0
        Hx = _mat_vec(H, self.x)
        y = _vec_sub(z, Hx)
        S = _add(_mul(_mul(H,self.P),_T(H)), R)
        # Kalman gain: K = P Hᵀ S⁻¹
        PHt = _mul(self.P, _T(H))
        if nz == 2: S_inv = _inv2(S)
        else:
            # 3x3 Cramer
            det = (S[0][0]*(S[1][1]*S[2][2]-S[1][2]*S[2][1])
                  -S[0][1]*(S[1][0]*S[2][2]-S[1][2]*S[2][0])
                  +S[0][2]*(S[1][0]*S[2][1]-S[1][1]*S[2][0]))
            if abs(det)<1e-12: return False
            cofactors=[[S[1][1]*S[2][2]-S[1][2]*S[2][1],-(S[0][1]*S[2][2]-S[0][2]*S[2][1]),S[0][1]*S[1][2]-S[0][2]*S[1][1]],
                        [-(S[1][0]*S[2][2]-S[1][2]*S[2][0]),S[0][0]*S[2][2]-S[0][2]*S[2][0],-(S[0][0]*S[1][2]-S[0][2]*S[1][0])],
                        [S[1][0]*S[2][1]-S[1][1]*S[2][0],-(S[0][0]*S[2][1]-S[0][1]*S[2][0]),S[0][0]*S[1][1]-S[0][1]*S[1][0]]]
            S_inv = [[cofactors[i][j]/det for j in range(3)] for i in range(3)]
        K = _mul(PHt, S_inv)
        Ky = _mat_vec(K, y)
        self.x = _vec_add(self.x, Ky)
        KH = _mul(K, H)
        IKH = _sub(_eye(6), KH)
        self.P = _mul(IKH, self.P)
        return True

# ── UKF (Unscented Kalman Filter) ────────────────────────────────────────────
class UKF:
    """Unscented Kalman Filter. State: [x,y,z,vx,vy,vz]."""

    def __init__(self, q: float = 1.0, r: float = 5.0) -> None:
        self.n = 6; self.x: Vec = [0.0]*self.n
        self.P: Mat = [[10.0 if i==j else 0.0 for j in range(self.n)] for i in range(self.n)]
        self._q = q; self._r = r
        alpha,beta,kappa = 1e-3, 2.0, 0.0
        lam = alpha**2*(self.n+kappa) - self.n
        self._lam = lam
        self._Wm = [lam/(self.n+lam)] + [0.5/(self.n+lam)]*(2*self.n)
        self._Wc = [lam/(self.n+lam)+(1-alpha**2+beta)] + [0.5/(self.n+lam)]*(2*self.n)

    def _sigma_pts(self) -> List[Vec]:
        L = _chol([[self.P[i][j]*(self.n+self._lam) for j in range(self.n)]
                   for i in range(self.n)])
        pts = [list(self.x)]
        for j in range(self.n):
            col = [L[i][j] for i in range(self.n)]
            pts.append(_vec_add(self.x, col))
            pts.append(_vec_sub(self.x, col))
        return pts

    def predict(self, dt: float) -> None:
        F = _eye(self.n)
        for i in range(3): F[i][i+3] = dt
        sigmas = self._sigma_pts()
        propagated = [_mat_vec(F, s) for s in sigmas]
        x_new = [sum(self._Wm[i]*propagated[i][j] for i in range(2*self.n+1)) for j in range(self.n)]
        Q = _zeros(self.n,self.n)
        for i in range(3):
            Q[i][i]=self._q*dt**2; Q[i+3][i+3]=self._q
        P_new = _zeros(self.n,self.n)
        for i in range(2*self.n+1):
            d = _vec_sub(propagated[i], x_new)
            for r in range(self.n):
                for c in range(self.n):
                    P_new[r][c] += self._Wc[i]*d[r]*d[c]
        self.P = _add(P_new, Q)
        self.x = x_new

    def update(self, z: Vec, R: Mat) -> bool:
        nz = len(z)
        sigmas = self._sigma_pts()
        zs = [[s[i] for i in range(nz)] for s in sigmas]
        z_mean = [sum(self._Wm[i]*zs[i][j] for i in range(2*self.n+1)) for j in range(nz)]
        Pzz = _zeros(nz,nz)
        Pxz = _zeros(self.n,nz)
        for i in range(2*self.n+1):
            dz = _vec_sub(zs[i], z_mean)
            dx = _vec_sub(sigmas[i], self.x)
            for r in range(nz):
                for c in range(nz): Pzz[r][c] += self._Wc[i]*dz[r]*dz[c]
            for r in range(self.n):
                for c in range(nz): Pxz[r][c] += self._Wc[i]*dx[r]*dz[c]
        S = _add(Pzz, R)
        if nz == 2: S_inv = _inv2(S)
        else:
            det=(S[0][0]*(S[1][1]*S[2][2]-S[1][2]*S[2][1])
                -S[0][1]*(S[1][0]*S[2][2]-S[1][2]*S[2][0])
                +S[0][2]*(S[1][0]*S[2][1]-S[1][1]*S[2][0]))
            if abs(det)<1e-12: return False
            S_inv=[[0.0]*nz for _ in range(nz)]  # simplified
            for i in range(nz): S_inv[i][i]=1.0/max(S[i][i],1e-12)
        K = _mul(Pxz, S_inv)
        innov = _vec_sub(z, z_mean)
        self.x = _vec_add(self.x, _mat_vec(K, innov))
        self.P = _sub(self.P, _mul(_mul(K,S), _T(K)))
        return True

# ── Particle Filter ───────────────────────────────────────────────────────────
class ParticleFilter:
    """Bootstrap Particle Filter. State per particle: [x,y,heading]."""

    def __init__(self, n_particles: int = 200, x0: float = 0.0, y0: float = 0.0) -> None:
        self._N = n_particles
        self._particles = [[x0, y0, 0.0] for _ in range(n_particles)]
        self._weights = [1.0/n_particles]*n_particles

    def predict(self, dt: float, q_sigma: float) -> None:
        for p in self._particles:
            p[0] += random.gauss(0, q_sigma*math.sqrt(dt))
            p[1] += random.gauss(0, q_sigma*math.sqrt(dt))
            p[2] += random.gauss(0, 0.01*dt)

    def update(self, z: Vec, sigma_obs: float) -> None:
        """z=[x_obs, y_obs]. Likelihood = Gaussian."""
        new_w = []
        for p, w in zip(self._particles, self._weights):
            dx = z[0]-p[0]; dy = z[1]-p[1]
            dist2 = dx**2+dy**2
            lkl = math.exp(-0.5*dist2/(sigma_obs**2+1e-9))
            new_w.append(w*lkl)
        s = sum(new_w)+1e-30
        self._weights = [w/s for w in new_w]
        self._resample()

    def _resample(self) -> None:
        """Systematic resampling."""
        N = self._N; cs = [0.0]*(N+1)
        for i,w in enumerate(self._weights): cs[i+1]=cs[i]+w
        new_p = []; step = 1.0/N; u0 = random.random()*step
        j = 0
        for i in range(N):
            u = u0+i*step
            while j<N-1 and cs[j+1]<u: j+=1
            new_p.append(list(self._particles[j]))
        self._particles = new_p
        self._weights = [1.0/N]*N

    @property
    def mean(self) -> Vec:
        mx=my=mh=0.0
        for p,w in zip(self._particles,self._weights):
            mx+=p[0]*w; my+=p[1]*w; mh+=p[2]*w
        return [mx,my,mh]

    @property
    def covariance(self) -> Mat:
        m=self.mean; C=_zeros(3,3)
        for p,w in zip(self._particles,self._weights):
            d=[p[i]-m[i] for i in range(3)]
            for r in range(3):
                for c in range(3): C[r][c]+=w*d[r]*d[c]
        return C

# ── SensorFusion ──────────────────────────────────────────────────────────────
class SensorFusion:
    """Covariance-weighted fusion of multi-tier Estimates."""

    def __init__(self, filter_type: str = "ekf") -> None:
        if filter_type not in ("ekf","ukf","pf","graph"):
            raise ValueError(f"unknown filter: {filter_type}")
        self.filter_type = filter_type
        self._ekf: Optional[EKF] = EKF() if filter_type=="ekf" else None
        self._history: List[Estimate] = []

    def fuse(self, estimates) -> Optional[Estimate]:
        ests = [e for e in estimates if e.confidence.valid]
        if not ests:
            return None
        # Covariance-weighted position average
        total_w = 0.0; lat=lon=alt=0.0
        for e in ests:
            w = 1.0/max(e.confidence.horizontal_m, 0.01)**2
            lat+=e.pose.position.lat*w; lon+=e.pose.position.lon*w
            alt+=e.pose.position.alt*w; total_w+=w
        lat/=total_w; lon/=total_w; alt/=total_w
        best_h = min(e.confidence.horizontal_m for e in ests)
        fused_h = best_h/math.sqrt(len(ests))
        est = Estimate(
            pose=Pose(Position(lat,lon,alt)),
            confidence=Confidence(horizontal_m=fused_h, vertical_m=fused_h*1.5,
                                   valid=True, source=f"fusion-{self.filter_type}"),
            source=f"fusion-{self.filter_type}",
            raw={"contributors":[e.source for e in ests]},
        )
        self._history.append(est)
        return est

    def reject_outliers(self, estimates, sigma: float = 3.0) -> List[Estimate]:
        if not estimates:
            return []
        lats=[e.pose.position.lat for e in estimates]
        lons=[e.pose.position.lon for e in estimates]
        n=len(lats)
        if n<2: return list(estimates)
        mlat=sum(lats)/n; mlon=sum(lons)/n
        slat=math.sqrt(sum((l-mlat)**2 for l in lats)/(n-1)+1e-9)
        slon=math.sqrt(sum((l-mlon)**2 for l in lons)/(n-1)+1e-9)
        return [e for e in estimates
                if abs(e.pose.position.lat-mlat)<=sigma*slat
                and abs(e.pose.position.lon-mlon)<=sigma*slon]

    def reset(self) -> None:
        self._history.clear()
        if self._ekf: self._ekf = EKF()

__all__ = ["EKF","UKF","ParticleFilter","SensorFusion"]
