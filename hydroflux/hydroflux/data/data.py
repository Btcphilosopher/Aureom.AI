"""
Data interfaces: read/write time-series resource data (river flow,
reservoir levels, tidal predictions, turbine curves, electricity prices,
demand, weather) via CSV, Parquet, JSON and NetCDF, without embedding any
proprietary dataset into the package itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

import pandas as pd

from hydroflux.core.timeseries import ResourceTimeSeries


def _infer_format(path: Union[str, Path]) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix in ("csv", "parquet", "json"):
        return suffix
    if suffix in ("nc", "netcdf", "nc4"):
        return "netcdf"
    raise ValueError(f"Cannot infer data format from extension '{suffix}'. Pass `format` explicitly.")


def read_timeseries(
    path: Union[str, Path],
    format: Optional[str] = None,
    time_col: str = "timestamp",
    tz: Optional[str] = None,
) -> pd.DataFrame:
    """Read a time-indexed table from CSV/Parquet/JSON/NetCDF into a
    ``pandas.DataFrame`` indexed by ``time_col``."""

    fmt = format or _infer_format(path)

    if fmt == "csv":
        df = pd.read_csv(path, parse_dates=[time_col])
        df = df.set_index(time_col)
    elif fmt == "parquet":
        try:
            df = pd.read_parquet(path)
        except ImportError as exc:
            raise ImportError("Parquet I/O requires `pyarrow`. Install with `pip install hydroflux[parquet]`.") from exc
        if time_col in df.columns:
            df[time_col] = pd.to_datetime(df[time_col])
            df = df.set_index(time_col)
    elif fmt == "json":
        raw = json.loads(Path(path).read_text())
        df = pd.DataFrame(raw)
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.set_index(time_col)
    elif fmt == "netcdf":
        try:
            import xarray as xr
        except ImportError as exc:
            raise ImportError("NetCDF I/O requires `xarray` and `netCDF4`. Install with `pip install hydroflux[netcdf]`.") from exc
        ds = xr.open_dataset(path)
        df = ds.to_dataframe()
    else:
        raise ValueError(f"Unsupported format '{fmt}'")

    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(f"Loaded data from {path} does not have a datetime index")
    if tz is not None:
        df.index = df.index.tz_localize(tz) if df.index.tz is None else df.index.tz_convert(tz)
    return df.sort_index()


def read_resource_timeseries(path: Union[str, Path], format: Optional[str] = None, time_col: str = "timestamp") -> ResourceTimeSeries:
    df = read_timeseries(path, format=format, time_col=time_col)
    return ResourceTimeSeries.from_frame(df, metadata={"source_path": str(path)})


def write_dataframe(df: pd.DataFrame, path: Union[str, Path], format: Optional[str] = None) -> None:
    fmt = format or _infer_format(path)
    if fmt == "csv":
        df.to_csv(path, index_label="timestamp")
    elif fmt == "parquet":
        try:
            df.to_parquet(path)
        except ImportError as exc:
            raise ImportError("Parquet I/O requires `pyarrow`. Install with `pip install hydroflux[parquet]`.") from exc
    elif fmt == "json":
        out = df.reset_index().rename(columns={df.index.name or "index": "timestamp"})
        out["timestamp"] = out["timestamp"].astype(str)
        Path(path).write_text(out.to_json(orient="records", indent=2))
    else:
        raise ValueError(f"Unsupported write format '{fmt}'")
