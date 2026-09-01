"""
HTTP API surface (spec item 63): factory state, production, machines,
materials, quality, energy, maintenance, battery products, simulation,
optimisation and economics -- all backed by the same engines the CLI and
dashboards use, so there is exactly one source of truth.

Requires the optional `api` extra (fastapi + uvicorn). Importing this
module without them raises a clear ImportError rather than partially
working, so ``pip install batteryfactory-4-0`` alone never breaks.

    uvicorn batteryfactory.api.app:app --reload

Security note (spec item 65): this API exposes the *digital twin's*
analytical state and mock/simulated data. It must never be wired to a real
industrial control system directly, and any real deployment needs the
RBAC/API-key layer in ``security.rbac`` in front of every route -- the
dependency is wired in below as a template, using an in-memory key store
that a real deployment must replace with a persisted one.
"""
from __future__ import annotations

try:
    from fastapi import Depends, FastAPI, Header, HTTPException
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "batteryfactory.api requires the 'api' extra: pip install batteryfactory-4-0[api]"
    ) from exc

from batteryfactory.core.factory_twin import FactoryDigitalTwin
from batteryfactory.economics.capex_opex import CapexInputs
from batteryfactory.security.rbac import ApiKeyAuth, RBAC, Role, User

app = FastAPI(title="BatteryFactory 4.0 API", version="0.1.0")

_twin = FactoryDigitalTwin.build_default(seed=1)
_auth = ApiKeyAuth()
_rbac = RBAC()
_demo_key = _auth.issue_key("demo-user")  # for local/dev use only


def get_current_user(x_api_key: str = Header(default="")) -> User:
    username = _auth.verify(x_api_key)
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return User(username=username, role=Role.EXECUTIVE)  # demo: single demo role


def require(resource: str):
    def _dep(user: User = Depends(get_current_user)) -> User:
        try:
            _rbac.check(user, resource)
        except Exception as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        return user
    return _dep


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/factory/state")
def factory_state(user: User = Depends(require("factory_state"))) -> dict:
    return _twin.current_state()


@app.post("/simulation/run")
def run_simulation(hours: float = 24.0, user: User = Depends(require("simulation"))) -> dict:
    result = _twin.run_simulation(hours=hours, capex=CapexInputs(0, 0, 0, 0, 0, 0, 0, 0, 0))
    return {
        "cells_completed": result.simulation.cells_completed,
        "modules_completed": result.simulation.modules_completed,
        "packs_completed": result.simulation.packs_completed,
        "pass_count": result.simulation.pass_count,
        "energy_kwh_per_cell": result.energy.kwh_per_cell,
        "cost_per_cell": result.unit_cost.cost_per_cell,
        "cost_per_kwh": result.unit_cost.cost_per_kwh,
        "ebitda": result.financials.ebitda,
        "top_bottleneck": result.bottlenecks[0].stage if result.bottlenecks else None,
        "safety_alarm_count": len(result.safety_alarms),
    }


@app.get("/machines")
def machines(user: User = Depends(require("machines"))) -> dict:
    return {
        mid: {"state": m.state.value, "utilisation_pct": m.utilisation_pct, "fault_count": m.fault_count}
        for mid, m in _twin.simulation_engine.machines.items()
    }


@app.get("/economics/unit-costs")
def unit_costs(user: User = Depends(require("economics"))) -> dict:
    result = _twin.run_simulation(hours=8.0, capex=CapexInputs(0, 0, 0, 0, 0, 0, 0, 0, 0))
    return {
        "cost_per_cell": result.unit_cost.cost_per_cell,
        "cost_per_kwh": result.unit_cost.cost_per_kwh,
        "cost_per_module": result.unit_cost.cost_per_module,
        "cost_per_pack": result.unit_cost.cost_per_pack,
        "breakdown_pct": result.unit_cost.breakdown_pct,
    }
