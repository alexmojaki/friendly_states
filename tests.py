from __future__ import annotations

from contextlib import contextmanager

import pytest

from friendly_states.core import AttributeState, IncorrectInitialState
from friendly_states.exceptions import StateChangedElsewhere


class TrafficLightMachine(AttributeState):
    is_machine = True

    class Summary:
        Green: [Yellow]
        Yellow: [Red]
        Red: [Green]


class Green(TrafficLightMachine):
    def slow_down(self) -> [Yellow]:
        pass


class Yellow(TrafficLightMachine):
    def stop(self) -> [Red]:
        pass


class Red(TrafficLightMachine):
    def go(self) -> [Green]:
        pass


TrafficLightMachine.complete()


class StatefulThing:
    def __init__(self, state):
        self.state = state


class OtherMachine(AttributeState):
    is_machine = True


class State1(OtherMachine):
    def to_2(self) -> [State2]:
        self.set_state(State1, State2)  # this is wrong


class State2(OtherMachine):
    def to_1(self) -> [State1]:
        pass


OtherMachine.complete()


@contextmanager
def raises(cls, **kwargs):
    with pytest.raises(cls) as exc_info:
        yield
    exc = exc_info.value
    for key, value in kwargs.items():
        assert getattr(exc, key) == value


def test_transitions():
    light = StatefulThing(Green)
    assert light.state is Green
    Green(light).slow_down()
    assert light.state is Yellow
    Yellow(light).stop()
    assert light.state is Red
    Red(light).go()
    assert light.state is Green
    with raises(IncorrectInitialState, instance=light, desired=Red, current=Green):
        Red(light)


def test_state_changed_elsewhere():
    obj = StatefulThing(State1)
    with raises(StateChangedElsewhere, instance=obj, current=State2, state=State1):
        State1(obj).to_2()


def test_attributes():
    assert Green.slug == "Green"
    assert Green.label == "Green"
    assert Green.output_states == {Yellow}
    assert Green.slow_down.output_states == {Yellow}
    assert TrafficLightMachine.states == {Green, Yellow, Red}
    assert OtherMachine.states == {State1, State2}


def test_graph():
    class Graph:
        Green: [Yellow, Red]
        Yellow: [Red]
        Red: [Green]

    with pytest.raises(AssertionError):
        TrafficLightMachine.check_graph(Graph)


def test_repr():
    assert repr(TrafficLightMachine) == "<class 'tests.TrafficLightMachine'>"
    assert repr(Green) == "Green"
