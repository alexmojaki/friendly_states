from __future__ import annotations

from django.db import models

from friendly_states.django import StateField, DjangoState


class TrafficLightMachine(DjangoState):
    is_machine = True

    class Summary:
        Green: [Yellow]
        Yellow: [Red]
        Red: [Green]


class Green(TrafficLightMachine):
    def to_yellow(self) -> [Yellow]:
        pass


class Yellow(TrafficLightMachine):
    def to_red(self) -> [Red]:
        pass


class Red(TrafficLightMachine):
    def to_green(self) -> [Green]:
        pass


TrafficLightMachine.complete()


class NullableMachine(DjangoState):
    is_machine = True


class NullableState(NullableMachine):
    pass


NullableMachine.complete()


class DefaultableMachine(DjangoState):
    is_machine = True


class DefaultableState(DefaultableMachine):
    pass


DefaultableMachine.complete()


class MyModel(models.Model):
    state = StateField(TrafficLightMachine)
    nullable_state = StateField(NullableMachine, null=True)
    defaultable_state = StateField(DefaultableMachine, default=DefaultableState)
