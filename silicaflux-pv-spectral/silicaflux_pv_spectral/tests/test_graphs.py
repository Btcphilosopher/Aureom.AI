import json

import pytest

from silicaflux_pv_spectral.graphs import GRAPH_NAMES, build_graph_data, render_graphs_matplotlib
from silicaflux_pv_spectral.io_utils import to_jsonable
from silicaflux_pv_spectral.materials import SILICON
from silicaflux_pv_spectral.pipeline import run_pipeline
from silicaflux_pv_spectral.spectrum import terrestrial_spectrum


@pytest.fixture(scope="module")
def pipeline_result():
    spectrum = terrestrial_spectrum()
    return run_pipeline(spectrum, SILICON)


def test_build_graph_data_returns_all_seven_graphs(pipeline_result):
    graphs = build_graph_data(pipeline_result)
    assert set(graphs.keys()) == set(GRAPH_NAMES)


def test_each_graph_series_matches_wavelength_grid_length(pipeline_result):
    graphs = build_graph_data(pipeline_result)
    for series in graphs.values():
        assert len(series.wavelength_nm) == len(series.values)
        assert len(series.wavelength_nm) == len(pipeline_result.spectrum.wavelength_nm)


def test_graph_series_bands_cover_uv_visible_nir(pipeline_result):
    graphs = build_graph_data(pipeline_result)
    series = graphs["EQE_GRAPH"]
    assert set(series.bands.keys()) == {"UV", "VISIBLE", "NIR"}


def test_graph_data_is_json_serialisable_via_io_utils(pipeline_result):
    graphs = build_graph_data(pipeline_result)
    payload = to_jsonable(graphs["EQE_GRAPH"])
    json.dumps(payload)  # must not raise
    assert len(payload["values"]) == len(pipeline_result.spectrum.wavelength_nm)


def test_render_graphs_matplotlib_degrades_or_succeeds_without_raising(tmp_path, pipeline_result):
    graphs = build_graph_data(pipeline_result)
    written = render_graphs_matplotlib(graphs, str(tmp_path))
    assert isinstance(written, list)
    if written:
        import os

        assert len(written) == len(GRAPH_NAMES)
        for path in written:
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
