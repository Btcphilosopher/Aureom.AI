import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from icecream_x.api.server import _recipes, _simulations, app  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_api_state():
    _recipes.clear()
    _simulations.clear()
    yield
    _recipes.clear()
    _simulations.clear()


@pytest.fixture
def client():
    return fastapi_testclient.TestClient(app)


def test_create_recipe_and_run_simulation(client):
    resp = client.post(
        "/create_recipe",
        json={
            "name": "Test Vanilla",
            "lines": [
                {"ingredient_name": "Whole Milk (3.5% fat)", "mass_kg": 40},
                {"ingredient_name": "Cream (40% fat)", "mass_kg": 25},
                {"ingredient_name": "Skim Milk", "mass_kg": 15},
                {"ingredient_name": "Sucrose", "mass_kg": 12},
                {"ingredient_name": "Glucose Syrup (42 DE)", "mass_kg": 5},
                {"ingredient_name": "Commercial Stabiliser/Emulsifier Blend", "mass_kg": 0.4},
            ],
        },
    )
    assert resp.status_code == 200
    recipe_id = resp.json()["recipe_id"]

    sim_resp = client.post("/run_simulation", json={"recipe_id": recipe_id})
    assert sim_resp.status_code == 200
    sim_id = sim_resp.json()["simulation_id"]
    assert sim_resp.json()["final_state"]["stage"] == "hardened"

    assert client.get(f"/get_state/{sim_id}").status_code == 200
    assert client.get(f"/get_energy/{sim_id}").status_code == 200
    assert client.get(f"/get_quality/{sim_id}").status_code == 200
    assert client.get(f"/get_microstructure/{sim_id}").status_code == 200


def test_create_recipe_rejects_unknown_ingredient(client):
    resp = client.post(
        "/create_recipe", json={"name": "Bad", "lines": [{"ingredient_name": "Unobtainium", "mass_kg": 1}]}
    )
    assert resp.status_code == 400


def test_get_state_404_for_unknown_simulation(client):
    resp = client.get("/get_state/999")
    assert resp.status_code == 404
