import numpy as np

from batteryfactory.datamodel.models import MachineState
from batteryfactory.machines.conveyor import Buffer, MaterialFlowNetwork
from batteryfactory.machines.machine_twin import MachineTwin, MachineTwinConfig
from batteryfactory.machines.robotics import RobotRole, RobotTwin


def test_machine_twin_transitions_are_gated():
    twin = MachineTwin(MachineTwinConfig("M1", "Test Machine", "test", cycle_time_s=1.0, rated_power_kw=10.0))
    assert twin.state == MachineState.OFFLINE
    assert not twin.transition(MachineState.RUNNING)  # can't skip STARTING
    assert twin.transition(MachineState.STARTING)
    assert twin.transition(MachineState.RUNNING)
    assert twin.state == MachineState.RUNNING


def test_machine_twin_accrues_runtime_and_energy_when_running():
    twin = MachineTwin(MachineTwinConfig("M2", "Test", "test", cycle_time_s=1.0, rated_power_kw=100.0),
                        rng=np.random.default_rng(0))
    twin.transition(MachineState.STARTING)
    twin.transition(MachineState.RUNNING)
    twin.step(2.0)
    assert twin.runtime_hours == 2.0
    assert twin.telemetry.energy_kwh_cumulative == 200.0


def test_buffer_starvation_and_blocking():
    buf = Buffer("b1", capacity=2)
    assert buf.pull() is None
    assert buf.starved_events == 1
    assert buf.push("x")
    assert buf.push("y")
    assert not buf.push("z")  # full
    assert buf.blocked_events == 1


def test_material_flow_network_bottleneck_buffer():
    net = MaterialFlowNetwork()
    a = net.add_buffer("a", capacity=10)
    b = net.add_buffer("b", capacity=10)
    for _ in range(8):
        a.push(1)
    for _ in range(2):
        b.push(1)
    assert net.bottleneck_buffer().buffer_id == "a"


def test_robot_twin_tracks_utilisation_and_faults():
    robot = RobotTwin("R1", RobotRole.ASSEMBLY, nominal_cycle_time_s=5.0, fault_rate_per_hr=0.5)
    rng = np.random.default_rng(1)
    for _ in range(50):
        robot.run_cycle(rng)
    assert robot.cycles_completed == 50
    assert robot.utilisation_pct > 0
