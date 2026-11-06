# results/ (generated, not version-controlled)

One directory per run (`results/<run_id>/`): `run.json` (record), `orfs/` (ORFS WORK_HOME:
inputs/config.mk + hooks, results/*.odb|*.v|*.sdc, logs, reports), `analysis/` (FloorplanLab
OpenDB/OpenSTA outputs), `export/` (geometry, connectivity, cells, DEF, images, TwinLab JSON),
`scripts_snapshot/` (the exact scripts the run executed), `previous_attempts/`.
`results/synth/<design>__<platform>__<key>/` is the shared synthesis; `results/sweeps/` holds
generated sweep configs and indexes; `results/_history/` the evidence of failed first attempts.
Regenerate with `make floorplan-sweep` / `make floorplan-route-estimate`; curated copies are in
`reports/`.
