from __future__ import annotations
import unittest

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


class TestStateMachine(unittest.TestCase):
    def test_transitions(self):
        light = TrafficLight()
        self.assertIs(light.state, Green)
        Green(light).slow_down()
        self.assertIs(light.state, Yellow)
        Yellow(light).stop()
        self.assertIs(light.state, Red)
        Red(light).go()
        self.assertIs(light.state, Green)
        with self.assertRaises(ValueError):
            Red(light)

    def test_attributes(self):
        self.assertEqual(Green.slug, "Green")
        self.assertEqual(Green.label, "Green")
        self.assertEqual(Green.output_states, {Yellow})
        self.assertEqual(Green.slow_down.output_names, ["Yellow"])
        self.assertEqual(TrafficLightMachine.states_set, {Green, Yellow, Red})
        self.assertEqual(TrafficLightMachine.name_to_state, {"Green": Green, "Yellow": Yellow, "Red": Red})
        self.assertEqual(TrafficLightMachine.slug_to_state, {"Green": Green, "Yellow": Yellow, "Red": Red})
        self.assertEqual(OtherMachine.states_set, {State1, State2})


if __name__ == '__main__':
    unittest.main()
