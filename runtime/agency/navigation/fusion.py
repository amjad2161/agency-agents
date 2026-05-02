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
    """Bootstrap Particle Filter. State per particle: [x,y,heading].

    Adds adaptive resampling (only when Neff drops below threshold), roughening
    (post-resample jitter to combat sample impoverishment), and a convergence
    metric for runtime monitoring.
    """

    def __init__(self, n_particles: int = 200, x0: float = 0.0, y0: float = 0.0) -> None:
        self._N = n_particles
        self._particles = [[x0, y0, 0.0] for _ in range(n_particles)]
        self._weights = [1.0/n_particles]*n_particles
        self._last_resampled: bool = False

    def predict(self, dt: float, q_sigma: float) -> None:
        for p in self._particles:
            p[0] += random.gauss(0, q_sigma*math.sqrt(dt))
            p[1] += random.gauss(0, q_sigma*math.sqrt(dt))
            p[2] += random.gauss(0, 0.01*dt)

    def update(self, z: Vec, sigma_obs: float) -> None:
        """z=[x_obs, y_obs]. Likelihood = Gaussian. Always resamples (legacy)."""
        self._reweight(z, sigma_obs)
        self._resample()
        self._last_resampled = True

    def _reweight(self, z: Vec, sigma_obs: float) -> None:
        new_w = []
        for p, w in zip(self._particles, self._weights):
            dx = z[0] - p[0]
            dy = z[1] - p[1]
            dist2 = dx * dx + dy * dy
            lkl = math.exp(-0.5 * dist2 / (sigma_obs * sigma_obs + 1e-9))
            new_w.append(w * lkl)
        s = sum(new_w) + 1e-30
        self._weights = [w / s for w in new_w]

    def neff(self) -> float:
        """Effective sample size: 1 / sum(w_i^2)."""
        s2 = sum(w * w for w in self._weights)
        return 1.0 / max(s2, 1e-30)

    def adaptive_resampling(
        self,
        z: Vec | None = None,
        sigma_obs: float | None = None,
        threshold_ratio: float = 0.5,
    ) -> bool:
        """Reweight (if observation given) and systematically resample only when
        Neff < threshold_ratio * N.  Returns True if resampling occurred.
        """
        if z is not None and sigma_obs is not None:
            self._reweight(z, sigma_obs)
        threshold = threshold_ratio * self._N
        did = False
        if self.neff() < threshold:
            self._resample()
            did = True
        self._last_resampled = did
        return did

    def roughening(self, K: float = 0.2) -> None:
        """Add scaled-Gaussian jitter to each state component to prevent sample
        impoverishment after resampling.  Sigma per dim is K * range / N^(1/d).
        """
        if not self._particles:
            return
        N = self._N
        d = len(self._particles[0])
        # range per dimension
        ranges = []
        for dim in range(d):
            vals = [p[dim] for p in self._particles]
            ranges.append(max(vals) - min(vals))
        denom = max(N ** (1.0 / max(d, 1)), 1e-9)
        sigmas = [K * r / denom for r in ranges]
        for p in self._particles:
            for dim in range(d):
                if sigmas[dim] > 0:
                    p[dim] += random.gauss(0.0, sigmas[dim])

    def convergence_metric(self) -> dict:
        """Return diagnostics: neff, entropy, max_weight."""
        neff = self.neff()
        max_w = max(self._weights) if self._weights else 0.0
        entropy = 0.0
        for w in self._weights:
            if w > 1e-30:
                entropy -= w * math.log(w)
        return {"neff": neff, "entropy": entropy, "max_weight": max_w}

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


class MapMatchingParticle(ParticleFilter):
    """Particle filter with map-matching constraints.

    Snaps particles to road / corridor segments from a VectorMapStore when they
    fall within ``snap_radius_m`` of a known segment.  Particles outside the
    radius keep their proposed state.
    """

    def __init__(
        self,
        n_particles: int = 200,
        x0: float = 0.0,
        y0: float = 0.0,
        snap_radius_m: float = 5.0,
    ) -> None:
        super().__init__(n_particles, x0, y0)
        self.snap_radius_m = float(snap_radius_m)

    def update_with_map(self, map_store) -> int:
        """Snap each particle's (x, y) to nearest map segment within radius.

        ``map_store`` must expose ``nearest_point(x, y)`` returning either
        ``(x_snap, y_snap, dist)`` or ``None`` when no segment is available.
        Returns the number of particles snapped.
        """
        snapped = 0
        for p in self._particles:
            try:
                hit = map_store.nearest_point(p[0], p[1])
            except Exception:
                hit = None
            if hit is None:
                continue
            x_snap, y_snap, dist = hit
            if dist <= self.snap_radius_m:
                p[0] = x_snap
                p[1] = y_snap
                snapped += 1
        return snapped

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

# ── AdaptiveEKF: Sage-Husa Q/R adaptation, χ² outlier reject, RAIM ──────────

# χ²(3, 0.95) — gate threshold for a 3-D measurement innovation.
CHI2_3_95 = 7.815


@dataclass
class RAIMResult:
    """Receiver Autonomous Integrity Monitoring result."""
    integrity_ok: bool
    horizontal_protection_level_m: float
    test_statistic: float
    threshold: float


class AdaptiveEKF(EKF):
    """EKF with innovation-based Q/R adaptation, χ² outlier rejection, and RAIM.

    Extends :class:`EKF` with three additions:

    * **Sage-Husa adaptation** updates ``_q`` and the diagonal of ``R`` using
      a forgetting-factor average of recent innovations.  This lets the
      filter respond when the underlying process or measurement noise
      changes mid-flight.
    * **χ² gating** rejects updates whose Mahalanobis-squared innovation
      exceeds ``CHI2_3_95``.  Rejected updates do not change the state.
    * **RAIM** turns the post-fit innovation magnitude into an HPL
      (horizontal protection level) and reports an integrity flag.

    The implementation only uses the per-measurement diagonal of S to keep
    behaviour deterministic and dependency-free.
    """

    def __init__(
        self,
        q: float = 1.0,
        r: float = 5.0,
        forgetting: float = 0.95,
        chi2_threshold: float = CHI2_3_95,
    ) -> None:
        super().__init__(q=q, r=r)
        self._forgetting = forgetting
        self._chi2 = chi2_threshold
        self._R_diag: list[float] = [r, r, r]
        self.last_innovation: Optional[Vec] = None
        self.last_test_statistic: float = 0.0
        self.outliers_rejected: int = 0
        self.updates_accepted: int = 0

    # -- helpers ------------------------------------------------------------
    def _mahalanobis_sq(self, innov: Vec, S_diag: list[float]) -> float:
        return sum(
            (innov[i] * innov[i]) / max(S_diag[i], 1e-9)
            for i in range(len(innov))
        )

    def _adapt_noise(self, innov: Vec) -> None:
        """Sage-Husa exponential-forgetting update of Q and R diagonals."""
        a = self._forgetting
        # R adaptation: track squared innovation per axis.
        for i in range(min(len(innov), len(self._R_diag))):
            self._R_diag[i] = a * self._R_diag[i] + (1 - a) * (innov[i] ** 2)
        # Q adaptation: scale process-noise scalar by mean squared innovation.
        mean_sq = sum(v * v for v in innov) / max(len(innov), 1)
        self._q = a * self._q + (1 - a) * mean_sq

    # -- override -----------------------------------------------------------
    def update(self, z: Vec, R: Optional[Mat] = None) -> bool:
        """χ²-gated EKF update with adaptive R.

        ``R`` may be passed explicitly (overrides the adaptive estimate for
        this step) or omitted to use the Sage-Husa estimate.
        """
        nz = len(z)
        if R is None:
            R = _zeros(nz, nz)
            for i in range(nz):
                R[i][i] = self._R_diag[i] if i < len(self._R_diag) else self._r

        # Pre-fit innovation
        H = _zeros(nz, 6)
        for i in range(nz):
            H[i][i] = 1.0
        Hx = _mat_vec(H, self.x)
        innov = _vec_sub(z, Hx)

        # Innovation covariance diagonal
        S_diag = [
            self.P[i][i] + (R[i][i] if i < len(R) else 0.0)
            for i in range(nz)
        ]
        ts = self._mahalanobis_sq(innov, S_diag)
        self.last_innovation = list(innov)
        self.last_test_statistic = ts

        if ts > self._chi2:
            self.outliers_rejected += 1
            return False

        ok = super().update(z, R)
        if ok:
            self.updates_accepted += 1
            self._adapt_noise(innov)
        return ok

    # -- RAIM ---------------------------------------------------------------
    def raim(self, hal_m: float = 50.0) -> RAIMResult:
        """Compute a horizontal protection level from current state covariance.

        ``hal_m`` is the Horizontal Alarm Limit; integrity passes when the
        HPL is below the alarm limit.
        """
        # 2-D position variance trace.
        var_xy = self.P[0][0] + self.P[1][1]
        # K factor for 1e-7 false-alarm in 2-D ≈ 5.33 (RTCA DO-229).
        k = 5.33
        hpl = k * math.sqrt(max(var_xy, 0.0))
        return RAIMResult(
            integrity_ok=hpl < hal_m,
            horizontal_protection_level_m=hpl,
            test_statistic=self.last_test_statistic,
            threshold=self._chi2,
        )


# ---------------------------------------------------------------------------
# Graph-SLAM pose graph optimizer (Round 3)
# ---------------------------------------------------------------------------

try:  # numpy is already a hard dep elsewhere in the package
    import numpy as _np
except Exception:  # pragma: no cover
    _np = None


@dataclass
class _PoseNode:
    pose_id: int
    x: float
    y: float
    theta: float


@dataclass
class _PoseConstraint:
    from_id: int
    to_id: int
    dx: float
    dy: float
    dtheta: float
    info: list  # 3x3 information matrix


def _wrap_pi(a: float) -> float:
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


class PoseGraphOptimizer:
    """2D pose-graph optimizer (Gauss-Newton on SE(2)).

    Nodes are (x, y, theta) poses indexed by ``pose_id``.  Edges are
    relative-motion constraints with a 3x3 information matrix.  ``optimize``
    runs Gauss-Newton iterations until the global cost change drops below
    ``1e-6`` or ``max_iterations`` is reached.

    Sparse linear solver uses ``numpy.linalg.solve`` on the dense
    information matrix — sufficient for the test-scale graphs used here.
    The first node added is anchored (gauge fixed) to remove the global
    translation/rotation freedom.
    """

    def __init__(self) -> None:
        if _np is None:  # pragma: no cover
            raise RuntimeError("PoseGraphOptimizer requires numpy")
        self._nodes: dict[int, _PoseNode] = {}
        self._order: list[int] = []
        self._edges: list[_PoseConstraint] = []
        self._last_cost: float = 0.0
        self._converged: bool = False

    # -- mutation -----------------------------------------------------------
    def add_pose(self, pose_id: int, x: float, y: float, theta: float) -> None:
        if pose_id in self._nodes:
            raise ValueError(f"pose {pose_id} already exists")
        self._nodes[pose_id] = _PoseNode(pose_id, float(x), float(y),
                                         _wrap_pi(float(theta)))
        self._order.append(pose_id)

    def add_constraint(
        self,
        from_id: int,
        to_id: int,
        dx: float,
        dy: float,
        dtheta: float,
        info_matrix: list,
    ) -> None:
        if from_id not in self._nodes or to_id not in self._nodes:
            raise ValueError("both endpoints must be added first")
        self._edges.append(_PoseConstraint(
            from_id, to_id,
            float(dx), float(dy), _wrap_pi(float(dtheta)),
            [list(row) for row in info_matrix],
        ))

    # -- optimization -------------------------------------------------------
    def _compute_residual_and_J(
        self, edge: _PoseConstraint,
    ):
        """Residual r and Jacobians J_i, J_j for one binary edge."""
        ni = self._nodes[edge.from_id]
        nj = self._nodes[edge.to_id]
        c, s = math.cos(ni.theta), math.sin(ni.theta)
        dx_w = nj.x - ni.x
        dy_w = nj.y - ni.y
        # measured - predicted (in i's frame)
        pred_dx =  c * dx_w + s * dy_w
        pred_dy = -s * dx_w + c * dy_w
        pred_dt = _wrap_pi(nj.theta - ni.theta)
        r = _np.array([
            edge.dx - pred_dx,
            edge.dy - pred_dy,
            _wrap_pi(edge.dtheta - pred_dt),
        ], dtype=float)
        # Jacobians (∂pred/∂x_i, ∂pred/∂x_j); residual = meas - pred so
        # ∂r/∂x_i = -∂pred/∂x_i.
        J_i = _np.array([
            [ c,  s, -s * dx_w + c * dy_w],
            [-s,  c, -c * dx_w - s * dy_w],
            [ 0,  0,  1.0],
        ], dtype=float)
        J_j = _np.array([
            [-c, -s, 0.0],
            [ s, -c, 0.0],
            [ 0,  0, -1.0],
        ], dtype=float)
        return r, J_i, J_j

    def optimize(self, max_iterations: int = 100, tol: float = 1e-6) -> dict:
        """Gauss-Newton optimization.  Returns diagnostics."""
        if not self._edges:
            return {"iterations": 0, "final_cost": 0.0,
                    "converged": True, "delta": 0.0}
        n = len(self._order)
        index = {pid: i for i, pid in enumerate(self._order)}
        prev_cost = float("inf")
        iters = 0
        converged = False
        delta_norm = float("inf")
        for iters in range(1, max_iterations + 1):
            H = _np.zeros((3 * n, 3 * n), dtype=float)
            b = _np.zeros(3 * n, dtype=float)
            cost = 0.0
            for edge in self._edges:
                r, J_i, J_j = self._compute_residual_and_J(edge)
                Omega = _np.array(edge.info, dtype=float)
                cost += float(r @ Omega @ r)
                i = index[edge.from_id]
                j = index[edge.to_id]
                # Block updates.
                Hii = J_i.T @ Omega @ J_i
                Hjj = J_j.T @ Omega @ J_j
                Hij = J_i.T @ Omega @ J_j
                bi = J_i.T @ Omega @ r
                bj = J_j.T @ Omega @ r
                H[3*i:3*i+3, 3*i:3*i+3] += Hii
                H[3*j:3*j+3, 3*j:3*j+3] += Hjj
                H[3*i:3*i+3, 3*j:3*j+3] += Hij
                H[3*j:3*j+3, 3*i:3*i+3] += Hij.T
                b[3*i:3*i+3] += bi
                b[3*j:3*j+3] += bj
            # Anchor first node — add identity block.
            H[0:3, 0:3] += _np.eye(3) * 1e6
            try:
                dx = _np.linalg.solve(H, -b)
            except _np.linalg.LinAlgError:
                break
            delta_norm = float(_np.linalg.norm(dx))
            for k, pid in enumerate(self._order):
                node = self._nodes[pid]
                node.x += float(dx[3*k])
                node.y += float(dx[3*k+1])
                node.theta = _wrap_pi(node.theta + float(dx[3*k+2]))
            if abs(prev_cost - cost) < tol:
                converged = True
                self._last_cost = cost
                break
            prev_cost = cost
            self._last_cost = cost
        self._converged = converged
        return {
            "iterations": iters,
            "final_cost": self._last_cost,
            "converged": converged,
            "delta": delta_norm,
        }

    # -- queries ------------------------------------------------------------
    def get_pose(self, pose_id: int) -> tuple:
        n = self._nodes[pose_id]
        return (n.x, n.y, n.theta)

    def detect_loop_closure(
        self,
        pose_id: int,
        radius_m: float = 10.0,
        min_id_gap: int = 5,
    ) -> list:
        """Return candidate pose IDs whose Euclidean distance from
        ``pose_id`` is below ``radius_m`` and whose index gap is at least
        ``min_id_gap`` (avoids matching neighbours along the trajectory).
        """
        if pose_id not in self._nodes:
            return []
        ref = self._nodes[pose_id]
        out = []
        for other_id, n in self._nodes.items():
            if other_id == pose_id:
                continue
            if abs(other_id - pose_id) < min_id_gap:
                continue
            d = math.hypot(n.x - ref.x, n.y - ref.y)
            if d <= radius_m:
                out.append(other_id)
        return out

    def marginal_covariance(self, pose_id: int) -> list:
        """Extract a 3x3 covariance block from the inverse of the joint
        information matrix accumulated at the last linearisation point.
        """
        if not self._edges or pose_id not in self._nodes:
            return [[0.0]*3 for _ in range(3)]
        n = len(self._order)
        index = {pid: i for i, pid in enumerate(self._order)}
        H = _np.zeros((3 * n, 3 * n), dtype=float)
        for edge in self._edges:
            _, J_i, J_j = self._compute_residual_and_J(edge)
            Omega = _np.array(edge.info, dtype=float)
            i = index[edge.from_id]
            j = index[edge.to_id]
            Hii = J_i.T @ Omega @ J_i
            Hjj = J_j.T @ Omega @ J_j
            Hij = J_i.T @ Omega @ J_j
            H[3*i:3*i+3, 3*i:3*i+3] += Hii
            H[3*j:3*j+3, 3*j:3*j+3] += Hjj
            H[3*i:3*i+3, 3*j:3*j+3] += Hij
            H[3*j:3*j+3, 3*i:3*i+3] += Hij.T
        H[0:3, 0:3] += _np.eye(3) * 1e6
        try:
            cov = _np.linalg.inv(H)
        except _np.linalg.LinAlgError:
            return [[0.0]*3 for _ in range(3)]
        k = index[pose_id]
        block = cov[3*k:3*k+3, 3*k:3*k+3]
        return block.tolist()

    @property
    def n_poses(self) -> int:
        return len(self._nodes)

    @property
    def n_edges(self) -> int:
        return len(self._edges)


# ---------------------------------------------------------------------------
# Generic factor graph (Round 4)
# ---------------------------------------------------------------------------


class FactorGraph:
    """Generic nonlinear least-squares factor graph.

    Supports unary (prior) and binary factors with user-supplied measurement
    functions ``h_func`` and information matrices.  Each factor's Jacobian
    is computed numerically by finite differences — keeps the harness
    dependency-free and works for any user-defined ``h_func``.

    Variables are flat numpy state vectors with declared dimensions.  The
    optimiser stacks all variables into a single state vector and runs
    Gauss-Newton with ``numpy.linalg.solve``.
    """

    def __init__(self) -> None:
        if _np is None:  # pragma: no cover
            raise RuntimeError("FactorGraph requires numpy")
        self._vars: dict = {}        # var_id -> dim
        self._values: dict = {}      # var_id -> ndarray
        self._order: list = []
        self._unary: list = []
        self._binary: list = []

    # -- variables ----------------------------------------------------------
    def add_variable(
        self,
        var_id,
        state_dim: int,
        initial: Optional["_np.ndarray"] = None,
    ) -> None:
        if var_id in self._vars:
            raise ValueError(f"variable {var_id} already exists")
        self._vars[var_id] = int(state_dim)
        self._values[var_id] = (
            _np.zeros(int(state_dim), dtype=float) if initial is None
            else _np.asarray(initial, dtype=float).reshape(int(state_dim)).copy()
        )
        self._order.append(var_id)

    def set_value(self, var_id, value) -> None:
        self._values[var_id] = _np.asarray(value, dtype=float).reshape(
            self._vars[var_id]
        ).copy()

    def get_value(self, var_id):
        return self._values[var_id].copy()

    # -- factors ------------------------------------------------------------
    def add_unary_factor(self, var_id, measurement, info_matrix, h_func) -> None:
        if var_id not in self._vars:
            raise ValueError(f"unknown var {var_id}")
        self._unary.append({
            "var": var_id,
            "z": _np.asarray(measurement, dtype=float),
            "info": _np.asarray(info_matrix, dtype=float),
            "h": h_func,
        })

    def add_binary_factor(
        self, var_id_1, var_id_2, measurement, info_matrix, h_func,
    ) -> None:
        if var_id_1 not in self._vars or var_id_2 not in self._vars:
            raise ValueError("unknown variables in binary factor")
        self._binary.append({
            "v1": var_id_1,
            "v2": var_id_2,
            "z": _np.asarray(measurement, dtype=float),
            "info": _np.asarray(info_matrix, dtype=float),
            "h": h_func,
        })

    # -- numerical Jacobian -------------------------------------------------
    @staticmethod
    def _num_jacobian(h, x, eps: float = 1e-5):
        h0 = _np.asarray(h(x), dtype=float)
        n = x.size
        m = h0.size
        J = _np.zeros((m, n), dtype=float)
        for i in range(n):
            xp = x.copy()
            xp[i] += eps
            J[:, i] = (_np.asarray(h(xp), dtype=float) - h0) / eps
        return h0, J

    @staticmethod
    def _num_jacobian2(h, x1, x2, eps: float = 1e-5):
        h0 = _np.asarray(h(x1, x2), dtype=float)
        m = h0.size
        J1 = _np.zeros((m, x1.size), dtype=float)
        J2 = _np.zeros((m, x2.size), dtype=float)
        for i in range(x1.size):
            xp = x1.copy(); xp[i] += eps
            J1[:, i] = (_np.asarray(h(xp, x2), dtype=float) - h0) / eps
        for i in range(x2.size):
            xp = x2.copy(); xp[i] += eps
            J2[:, i] = (_np.asarray(h(x1, xp), dtype=float) - h0) / eps
        return h0, J1, J2

    # -- optimization -------------------------------------------------------
    def _index_map(self):
        idx = {}
        offset = 0
        for vid in self._order:
            d = self._vars[vid]
            idx[vid] = (offset, offset + d)
            offset += d
        return idx, offset

    def optimize(self, max_iter: int = 50, tol: float = 1e-6) -> dict:
        idx, n = self._index_map()
        prev_cost = float("inf")
        iters = 0
        converged = False
        last_cost = 0.0
        for iters in range(1, max_iter + 1):
            H = _np.zeros((n, n), dtype=float)
            b = _np.zeros(n, dtype=float)
            cost = 0.0
            for f in self._unary:
                x = self._values[f["var"]]
                h0, J = self._num_jacobian(f["h"], x)
                r = h0 - f["z"]
                Omega = f["info"]
                cost += float(r @ Omega @ r)
                a, c = idx[f["var"]]
                H[a:c, a:c] += J.T @ Omega @ J
                b[a:c] += J.T @ Omega @ r
            for f in self._binary:
                x1 = self._values[f["v1"]]
                x2 = self._values[f["v2"]]
                h0, J1, J2 = self._num_jacobian2(f["h"], x1, x2)
                r = h0 - f["z"]
                Omega = f["info"]
                cost += float(r @ Omega @ r)
                a1, c1 = idx[f["v1"]]
                a2, c2 = idx[f["v2"]]
                H[a1:c1, a1:c1] += J1.T @ Omega @ J1
                H[a2:c2, a2:c2] += J2.T @ Omega @ J2
                H12 = J1.T @ Omega @ J2
                H[a1:c1, a2:c2] += H12
                H[a2:c2, a1:c1] += H12.T
                b[a1:c1] += J1.T @ Omega @ r
                b[a2:c2] += J2.T @ Omega @ r
            H = H + _np.eye(n) * 1e-6
            try:
                dx = _np.linalg.solve(H, -b)
            except _np.linalg.LinAlgError:
                break
            for vid in self._order:
                a, c = idx[vid]
                self._values[vid] = self._values[vid] + dx[a:c]
            last_cost = cost
            if abs(prev_cost - cost) < tol:
                converged = True
                break
            prev_cost = cost
        return {
            "iterations": iters,
            "final_cost": last_cost,
            "converged": converged,
        }

    def marginal(self, var_id) -> dict:
        idx, n = self._index_map()
        if var_id not in idx:
            raise ValueError(f"unknown var {var_id}")
        H = _np.zeros((n, n), dtype=float)
        for f in self._unary:
            x = self._values[f["var"]]
            _, J = self._num_jacobian(f["h"], x)
            a, c = idx[f["var"]]
            H[a:c, a:c] += J.T @ f["info"] @ J
        for f in self._binary:
            x1 = self._values[f["v1"]]
            x2 = self._values[f["v2"]]
            _, J1, J2 = self._num_jacobian2(f["h"], x1, x2)
            a1, c1 = idx[f["v1"]]; a2, c2 = idx[f["v2"]]
            H[a1:c1, a1:c1] += J1.T @ f["info"] @ J1
            H[a2:c2, a2:c2] += J2.T @ f["info"] @ J2
            H12 = J1.T @ f["info"] @ J2
            H[a1:c1, a2:c2] += H12
            H[a2:c2, a1:c1] += H12.T
        H = H + _np.eye(n) * 1e-6
        try:
            cov = _np.linalg.inv(H)
        except _np.linalg.LinAlgError:
            return {"mean": self._values[var_id].copy(),
                    "cov": _np.eye(self._vars[var_id])}
        a, c = idx[var_id]
        return {
            "mean": self._values[var_id].copy(),
            "cov": cov[a:c, a:c],
        }

    @staticmethod
    def build_nav_graph(
        gps_obs: list,
        imu_preint: list,
        baro_obs: list,
    ) -> "FactorGraph":
        """Build a small navigation graph: variables are 3-D positions per
        keyframe; GPS provides unary priors, baro provides z-only unary
        priors, IMU provides binary position-difference priors.
        """
        n_keyframes = max(len(gps_obs), len(imu_preint) + 1, len(baro_obs))
        g = FactorGraph()
        for k in range(n_keyframes):
            g.add_variable(("p", k), 3,
                           initial=_np.zeros(3, dtype=float))
        info3 = _np.eye(3) * 100.0
        info1 = _np.array([[100.0]])
        # Unary GPS priors.
        for k, z in enumerate(gps_obs):
            if z is None:
                continue
            g.add_unary_factor(
                ("p", k),
                _np.asarray(z, dtype=float),
                info3,
                lambda x: x,
            )
        # Unary baro priors (z component).
        for k, z in enumerate(baro_obs):
            if z is None:
                continue
            g.add_unary_factor(
                ("p", k),
                _np.array([float(z)]),
                info1,
                lambda x: x[2:3],
            )
        # Binary IMU priors on Δp.
        for k, dp in enumerate(imu_preint):
            if dp is None:
                continue
            g.add_binary_factor(
                ("p", k),
                ("p", k + 1),
                _np.asarray(dp, dtype=float),
                info3,
                lambda x1, x2: x2 - x1,
            )
        return g


# =====================================================================
# GODSKILL Nav R6 — Interacting Multiple Model (IMM) Filter
# =====================================================================

class IMMFilter:
    """Interacting Multiple Model filter (CV + CT).

    Two motion models — constant velocity and constant turn-rate —
    blended via Markov-chain model probabilities updated by the
    measurement likelihood.

    State per model: [x, y, vx, vy] (CV) and [x, y, vx, vy, omega] (CT
    with omega projected back to a 4-state for the merged output).
    """

    def __init__(self, dt: float = 1.0,
                 q_cv: float = 0.1,
                 q_ct: float = 0.5,
                 r_pos: float = 1.0,
                 turn_rate_rad_s: float = 0.1,
                 trans_matrix=None,
                 init_probs=None) -> None:
        import numpy as _np
        self.dt = float(dt)
        self.q_cv = float(q_cv)
        self.q_ct = float(q_ct)
        self.r_pos = float(r_pos)
        self.omega = float(turn_rate_rad_s)
        # Per-model 4-D state and 4x4 covariance
        self.x_cv = _np.zeros(4)
        self.x_ct = _np.zeros(4)
        self.P_cv = _np.eye(4) * 10.0
        self.P_ct = _np.eye(4) * 10.0
        if trans_matrix is None:
            # Sticky models (95% stay, 5% switch)
            self.trans = _np.array([[0.95, 0.05], [0.05, 0.95]])
        else:
            self.trans = _np.asarray(trans_matrix, dtype=float)
        if init_probs is None:
            self.mu = _np.array([0.5, 0.5])
        else:
            self.mu = _np.asarray(init_probs, dtype=float)
            self.mu /= self.mu.sum()
        self._merged_state = _np.zeros(4)
        self._merged_P = _np.eye(4) * 10.0

    @property
    def model_probabilities(self):
        import numpy as _np
        return _np.asarray(self.mu, dtype=float).copy()

    def _F_cv(self):
        import numpy as _np
        dt = self.dt
        return _np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=float)

    def _F_ct(self, omega: float):
        import numpy as _np
        dt = self.dt
        if abs(omega) < 1e-6:
            return self._F_cv()
        s = math.sin(omega * dt)
        c = math.cos(omega * dt)
        return _np.array([
            [1, 0, s / omega, -(1 - c) / omega],
            [0, 1, (1 - c) / omega, s / omega],
            [0, 0, c, -s],
            [0, 0, s, c],
        ], dtype=float)

    def _Q(self, q: float):
        import numpy as _np
        dt = self.dt
        q4 = _np.array([
            [dt ** 4 / 4, 0, dt ** 3 / 2, 0],
            [0, dt ** 4 / 4, 0, dt ** 3 / 2],
            [dt ** 3 / 2, 0, dt ** 2, 0],
            [0, dt ** 3 / 2, 0, dt ** 2],
        ], dtype=float)
        return q4 * q

    def predict(self, dt: Optional[float] = None):
        import numpy as _np
        if dt is not None:
            self.dt = float(dt)
        # 1. Mixing probabilities
        cbar = self.trans.T @ self.mu  # normalising
        cbar = _np.maximum(cbar, 1e-12)
        mix = (self.trans * self.mu[:, None]) / cbar[None, :]
        # 2. Mixed initial conditions per model
        states = [self.x_cv, self.x_ct]
        Ps = [self.P_cv, self.P_ct]
        x0 = [_np.zeros(4), _np.zeros(4)]
        P0 = [_np.zeros((4, 4)), _np.zeros((4, 4))]
        for j in range(2):
            for i in range(2):
                x0[j] = x0[j] + mix[i, j] * states[i]
            for i in range(2):
                d = states[i] - x0[j]
                P0[j] = P0[j] + mix[i, j] * (Ps[i] + _np.outer(d, d))
        # 3. Per-model prediction
        F0 = self._F_cv()
        F1 = self._F_ct(self.omega)
        self.x_cv = F0 @ x0[0]
        self.P_cv = F0 @ P0[0] @ F0.T + self._Q(self.q_cv)
        self.x_ct = F1 @ x0[1]
        self.P_ct = F1 @ P0[1] @ F1.T + self._Q(self.q_ct)
        # 4. Merge for output
        self._merged_state = self.mu[0] * self.x_cv + self.mu[1] * self.x_ct
        self._merged_P = _np.zeros((4, 4))
        for i, (xi, Pi) in enumerate([(self.x_cv, self.P_cv),
                                      (self.x_ct, self.P_ct)]):
            d = xi - self._merged_state
            self._merged_P = self._merged_P + self.mu[i] * (Pi + _np.outer(d, d))
        return self._merged_state.copy()

    def update(self, measurement):
        import numpy as _np
        z = _np.asarray(measurement, dtype=float).reshape(-1)
        if z.size != 2:
            raise ValueError("measurement must be (x, y) position")
        H = _np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
        R = _np.eye(2) * self.r_pos
        likelihoods = _np.zeros(2)
        for j, (x, P) in enumerate([(self.x_cv, self.P_cv),
                                    (self.x_ct, self.P_ct)]):
            S = H @ P @ H.T + R
            S = (S + S.T) * 0.5
            try:
                S_inv = _np.linalg.inv(S)
            except _np.linalg.LinAlgError:
                S_inv = _np.linalg.pinv(S)
            innov = z - H @ x
            K = P @ H.T @ S_inv
            x_new = x + K @ innov
            P_new = (_np.eye(4) - K @ H) @ P
            det = max(float(_np.linalg.det(2 * math.pi * S)), 1e-30)
            mahal = float(innov @ S_inv @ innov)
            likelihoods[j] = math.exp(-0.5 * mahal) / math.sqrt(det)
            if j == 0:
                self.x_cv, self.P_cv = x_new, P_new
            else:
                self.x_ct, self.P_ct = x_new, P_new
        # Update model probabilities
        cbar = self.trans.T @ self.mu
        new_mu = likelihoods * cbar
        s = float(new_mu.sum())
        if s < 1e-30:
            new_mu = _np.array([0.5, 0.5])
        else:
            new_mu = new_mu / s
        self.mu = new_mu
        # Merge
        self._merged_state = self.mu[0] * self.x_cv + self.mu[1] * self.x_ct
        self._merged_P = _np.zeros((4, 4))
        for i, (xi, Pi) in enumerate([(self.x_cv, self.P_cv),
                                      (self.x_ct, self.P_ct)]):
            d = xi - self._merged_state
            self._merged_P = self._merged_P + self.mu[i] * (Pi + _np.outer(d, d))
        return {
            "state": self._merged_state.copy(),
            "covariance": self._merged_P.copy(),
            "model_probabilities": self.mu.copy(),
            "likelihoods": likelihoods.copy(),
        }


__all__ = ["EKF","UKF","ParticleFilter","SensorFusion",
           "AdaptiveEKF","RAIMResult","CHI2_3_95",
           "PoseGraphOptimizer","FactorGraph","IMMFilter"]
