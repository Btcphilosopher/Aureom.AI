# rendering/ — GPU renderer (deferred)

Spec sections 42-46, 74-80: terrain/water/vegetation/unit rendering,
camera systems, LOD, cinematic cameras, UI, audio.

Not implemented. `python/simulation/` produces everything a renderer
would need to read (`World.query(...)`, `TerrainCell` elevation/biome/
resource data, `Calendar`/`WeatherSystem` state) without ever being
written to by rendering code — see `../docs/ARCHITECTURE.md` → "What a
rendering/multiplayer/editor layer would consume."
