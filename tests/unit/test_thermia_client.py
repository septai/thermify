from __future__ import annotations

from adapters.thermia_client import ThermiaClient


class DummyThermia:
    def __init__(self, username: str, password: str) -> None:
        _ = username
        _ = password
        self.connected = True
        self.heat_pumps = [FakeHeatPump()]


class FakeHeatPump:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def set_temperature(self, target_temperature: int) -> None:
        self.calls.append(target_temperature)


def test_set_target_temperature_sends_integer_to_pump() -> None:
    client = ThermiaClient("user", "pass", thermia_factory=DummyThermia)

    client.set_target_temperature(21)

    assert client._heat_pump.calls == [21, 21]


def test_set_target_temperature_does_not_write_in_demo_mode() -> None:
    client = ThermiaClient("user", "pass", thermia_factory=DummyThermia, demo_mode=True)

    client.set_target_temperature(21)

    assert client._heat_pump.calls == []
