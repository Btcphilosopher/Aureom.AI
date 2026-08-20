"""
Warp (thread-group) state and scheduling policies.

A warp is a group of ``warp_size`` SIMT threads that execute in lockstep.
This module tracks each warp's program counter, active-lane mask (which
shrinks under branch divergence and re-converges at a reconvergence point),
and readiness state, and implements a few real scheduling heuristics used
by hardware warp schedulers.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional

from .instruction_pipeline import Instruction, OpCode


class WarpState(Enum):
    READY = auto()
    STALLED_EXEC = auto()      # waiting on a result (ALU pipeline latency)
    STALLED_MEMORY = auto()    # waiting on a load/store to complete
    STALLED_BARRIER = auto()   # waiting on __syncthreads()-style barrier
    DONE = auto()


@dataclass
class Warp:
    warp_id: int
    sm_id: int
    block_id: int
    warp_size: int
    instructions: List[Instruction]
    pc: int = 0
    active_mask: int = 0
    state: WarpState = WarpState.READY
    ready_at_cycle: int = 0
    issue_count: int = 0
    stall_cycles_exec: int = 0
    stall_cycles_memory: int = 0
    divergence_events: int = 0
    created_cycle: int = 0
    outstanding_memory_ops: int = 0

    def __post_init__(self) -> None:
        if self.active_mask == 0:
            self.active_mask = (1 << self.warp_size) - 1

    def active_lane_count(self) -> int:
        return bin(self.active_mask).count("1")

    def is_finished(self) -> bool:
        return self.pc >= len(self.instructions) or self.state == WarpState.DONE

    def current_instruction(self) -> Optional[Instruction]:
        if self.is_finished():
            return None
        return self.instructions[self.pc]

    def apply_divergence(self, rng: random.Random, divergence_probability: float) -> None:
        """Randomly shrink the active mask on a divergent branch, modelling
        SIMT lane divergence. Reconvergence happens after a fixed number of
        instructions (modelled implicitly by masks resetting on BARRIER)."""
        instr = self.current_instruction()
        if instr is None or instr.opcode != OpCode.BRANCH:
            return
        if rng.random() < divergence_probability:
            full = (1 << self.warp_size) - 1
            # Keep a random non-empty subset of currently active lanes taking
            # the "taken" path this cycle; hardware serialises the rest.
            new_mask = 0
            for lane in range(self.warp_size):
                bit = 1 << lane
                if self.active_mask & bit and rng.random() < 0.5:
                    new_mask |= bit
            if new_mask == 0:
                new_mask = self.active_mask & -self.active_mask  # keep >=1 lane
            self.active_mask = new_mask
            self.divergence_events += 1
        else:
            self.active_mask = (1 << self.warp_size) - 1

    def advance_pc(self) -> None:
        self.pc += 1
        if self.pc >= len(self.instructions):
            self.state = WarpState.DONE


class SchedulingPolicy(Enum):
    GREEDY_THEN_OLDEST = "gto"
    ROUND_ROBIN = "rr"
    LOOSE_ROUND_ROBIN = "lrr"


@dataclass
class WarpScheduler:
    """One warp scheduler port belonging to an SM sub-partition. Selects up
    to ``issue_width`` ready warps per cycle according to a policy."""

    scheduler_id: int
    issue_width: int = 1
    policy: SchedulingPolicy = SchedulingPolicy.GREEDY_THEN_OLDEST
    warps: Dict[int, Warp] = field(default_factory=dict)
    _rr_cursor: int = 0
    stall_cycles_no_ready_warp: int = 0

    def add_warp(self, warp: Warp) -> None:
        self.warps[warp.warp_id] = warp

    def remove_finished(self) -> List[int]:
        done = [wid for wid, w in self.warps.items() if w.is_finished()]
        for wid in done:
            del self.warps[wid]
        return done

    def ready_warps(self, cycle: int) -> List[Warp]:
        return [
            w for w in self.warps.values()
            if w.state == WarpState.READY and w.ready_at_cycle <= cycle and not w.is_finished()
        ]

    def select(self, cycle: int) -> List[Warp]:
        ready = self.ready_warps(cycle)
        if not ready:
            self.stall_cycles_no_ready_warp += 1
            return []

        if self.policy == SchedulingPolicy.GREEDY_THEN_OLDEST:
            ready.sort(key=lambda w: (-w.issue_count, w.created_cycle))
        elif self.policy == SchedulingPolicy.ROUND_ROBIN:
            ready.sort(key=lambda w: w.warp_id)
            if ready:
                order = sorted(self.warps.keys())
                start = self._rr_cursor % len(order)
                rotated = order[start:] + order[:start]
                ready = [self.warps[wid] for wid in rotated if wid in {w.warp_id for w in ready}]
                self._rr_cursor += 1
        else:  # LOOSE_ROUND_ROBIN: like RR but only advances cursor on issue
            ready.sort(key=lambda w: (w.warp_id + self._rr_cursor) % max(1, len(self.warps)))

        return ready[: self.issue_width]

    def occupancy(self, max_warps: int) -> float:
        if max_warps <= 0:
            return 0.0
        return len(self.warps) / max_warps
