from __future__ import annotations

from contextlib import contextmanager

import pytest

from friendly_states.core import AttributeState, IncorrectInitialState
from friendly_states.exceptions import StateChangedElsewhere, IncorrectSummary, MultipleMachineAncestors, \
    InheritedFromState


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

    def __repr__(self):
        return f"{self.__class__.__name__}(state={self.state})"


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
def raises(cls, match=None, **kwargs):
    with pytest.raises(cls, match=match) as exc_info:
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
    with raises(
            IncorrectInitialState,
            instance=light,
            desired=Red,
            current=Green,
            message='StatefulThing(state=Green) should be in state Red but is actually in state Green',
    ):
        Red(light)


def test_state_changed_elsewhere():
    obj = StatefulThing(State1)
    with raises(
            StateChangedElsewhere,
            instance=obj,
            current=State2,
            state=State1,
            message="The state of StatefulThing(state=State2) has changed to State2 "
                    "since instantiating State1. "
                    "Did you change the state inside a transition method? Don't.",
    ):
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

    with raises(
            IncorrectSummary,
            message="""
Wrong outputs:

Outputs of Green:
According to summary       : Red, Yellow
According to actual classes: Yellow

"""):
        TrafficLightMachine.check_graph(Graph)


def test_repr():
    assert repr(TrafficLightMachine) == "<class 'tests.TrafficLightMachine'>"
    assert repr(Green) == "Green"


def test_abstract_classes():
    class MyMachine(AttributeState):
        is_machine = True

        class Summary:
            Loner: [Child1]
            Child1: [Loner, Child2]
            Child2: [Loner, Child1]

    class Loner(MyMachine):
        def to_child1(self) -> [Child1]:
            pass

    class Parent(MyMachine):
        is_abstract = True
        x = 9

        def to_loner(self) -> [Loner]:
            pass

        def foo(self) -> Loner:
            return Loner(None)

        def bar(self):
            pass

    class Mixin:
        pass

    class Child1(Mixin, Parent):
        def to_child2(self) -> [Child2]:
            pass

    class Child2(Parent):
        def to_child1(self) -> [Child1]:
            pass

    MyMachine.complete()


def test_multiple_machines():
    class Machine1(AttributeState):
        is_machine = True

    with raises(
            MultipleMachineAncestors,
            message=("Multiple machine classes found in ancestors of "
                     "<class 'tests.test_multiple_machines.<locals>.Machine2'>: "
                     "[<class 'tests.test_multiple_machines.<locals>.Machine2'>,"
                     " <class 'tests.test_multiple_machines.<locals>.Machine1'>]")
    ):
        class Machine2(Machine1):
            is_machine = True

        str(Machine2)

    class Machine3(AttributeState):
        is_machine = True

    class Machine4(AttributeState):
        is_machine = True

    with raises(
            MultipleMachineAncestors,
            machine_classes=[Machine3, Machine4],
            message=("Multiple machine classes found in ancestors of "
                     "<class 'tests.test_multiple_machines.<locals>.State'>: "
                     "[<class 'tests.test_multiple_machines.<locals>.Machine3'>,"
                     " <class 'tests.test_multiple_machines.<locals>.Machine4'>]"),
    ):
        class State(Machine3, Machine4):
            pass

        str(State)


def test_inherit_from_state():
    class MyMachine(AttributeState):
        is_machine = True

    class S1(MyMachine):
        pass

    with raises(
            InheritedFromState,
            ancestor=S1,
            machine=MyMachine,
            message=("<class 'tests.test_inherit_from_state.<locals>.S2'> "
                     "inherits from <class 'tests.test_inherit_from_state.<locals>.S1'> "
                     "and both are part of the machine "
                     "<class 'tests.test_inherit_from_state.<locals>.MyMachine'>, "
                     "but <class 'tests.test_inherit_from_state.<locals>.S1'> is not abstract. "
                     "If it should be, mark it with is_abstract = True. "
                     "You cannot inherit from actual state classes."),
    ):
        class S2(S1):
            pass

        str(S2)


def test_complete_non_machine():
    with pytest.raises(ValueError):
        AttributeState.complete()
