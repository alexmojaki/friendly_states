from __future__ import annotations

import pytest

from friendly_states.core import State


class TrafficLightMachine(State):
    is_machine = True


class Green(TrafficLightMachine):
    def slow_down(self) -> [Yellow]:
        pass


class Yellow(TrafficLightMachine):
    def stop(self) -> [Red]:
        pass


class Red(TrafficLightMachine):
    def go(self) -> [Green]:
        pass


class TrafficLight:
    def __init__(self):
        self.state = Green


class OtherMachine(State):
    is_machine = True


class State1(OtherMachine):
    def to_2(self) -> [State2]:
        pass


class State2(OtherMachine):
    def to_1(self) -> [State1]:
        pass


def test_transitions():
    light = TrafficLight()
    assert light.state is Green
    Green(light).slow_down()
    assert light.state is Yellow
    Yellow(light).stop()
    assert light.state is Red
    Red(light).go()
    assert light.state is Green
    with pytest.raises(ValueError):
        Red(light)


def test_attributes():
    assert Green.slug == "Green"
    assert Green.label == "Green"
    assert Green.output_states == {Yellow}
    assert Green.slow_down.output_names == ["Yellow"]
    assert TrafficLightMachine.states_set == {Green, Yellow, Red}
    assert TrafficLightMachine.name_to_state == {"Green": Green, "Yellow": Yellow, "Red": Red}
    assert TrafficLightMachine.slug_to_state == {"Green": Green, "Yellow": Yellow, "Red": Red}
    assert OtherMachine.states_set == {State1, State2}
