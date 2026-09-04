# engine/ — native performance core (deferred)

Spec section 66: pathfinding, combat, crowd simulation, and spatial
indexing are designed to move here as Rust or C++ once entity counts
outgrow what `python/simulation/` can do at interactive framerates.

Not implemented yet. See `../docs/ARCHITECTURE.md` → "Native performance
core" for exactly which Python modules (`pathfinding/astar.py`,
`military/combat.py`) are the first candidates and why they were written
to be portable (plain data in, plain data out, no hidden global state).
