# multiplayer/ — networking & replication (deferred)

Spec section 63: CLIENT → COMMAND → AUTHORITATIVE SIMULATION → STATE
REPLICATION.

Not implemented. The simulation core already speaks this architecture:
`GameState.submit_command()` takes a `Command` (a plain, serializable
dataclass), and `GameState.tick()` is the sole authoritative mutator. A
network layer's job would be transporting `Command`s to the authoritative
`GameState` and broadcasting `GameState.snapshot()` deltas to clients —
no simulation code would need to change. See
`../docs/ARCHITECTURE.md`.
