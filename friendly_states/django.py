from django.core.exceptions import ValidationError
from django.db import models

from friendly_states.core import StateMeta, AttributeState


class DjangoState(AttributeState):
    auto_save = True

    def set_state(self, previous_state, new_state):
        super().set_state(previous_state, new_state)
        if self.auto_save:
            self.inst.save()


class StateField(models.CharField):
    def __init__(self, machine, *args, **kwargs):
        if not machine.is_machine:
            raise ValueError(f"{machine} is not a state machine root")

        self.machine = machine
        kwargs["max_length"] = 64
        kwargs.setdefault("verbose_name", machine.label)
        kwargs["choices"] = [
            (state.slug, state.label)
            for state in machine.slug_to_state.values()
        ]
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs["max_length"]
        del kwargs["choices"]
        if kwargs["verbose_name"] == self.machine.label:
            del kwargs["verbose_name"]

        return name, path, (self.machine,), kwargs

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        machine = self.machine
        if value is None or value in machine.states:
            return value

        if isinstance(value, StateMeta):
            raise ValidationError(
                f"{value} is a state class but isn't one of the states "
                f"in the machine {machine.__name__}, which are {machine.states}",
            )

        if not isinstance(value, str):
            raise ValidationError(
                f"{self.name} should be a state class, a string, or None",
            )

        try:
            return machine.slug_to_state[value]
        except KeyError:
            pass

        raise ValidationError(
            f"{value} is not one of the valid slugs for this machine: "
            f"{sorted(state.slug for state in machine.states)}",
        )

    def get_prep_value(self, value):
        if isinstance(value, StateMeta):
            return value.slug
        return value

    def get_db_prep_value(self, value, connection, prepared=False):
        return self.get_prep_value(value)

    def value_to_string(self, obj):
        return self.get_prep_value(obj)
