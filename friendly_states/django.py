from django.core.exceptions import ValidationError
from django.db import models

from friendly_states.core import StateMeta, AttributeState


class DjangoState(AttributeState):
    attr_name = None
    auto_save = True

    def set_state(self, previous_state, new_state):
        super().set_state(previous_state, new_state)
        if self.auto_save:
            self.inst.save()


class StateField(models.CharField):
    empty_strings_allowed = False

    def __init__(self, machine, *args, **kwargs):
        if not (isinstance(machine, StateMeta) and machine.is_machine):
            raise ValueError(f"{machine} is not a state machine root")

        if not issubclass(machine, DjangoState):
            raise TypeError(f"The state machine must be a subclass of DjangoState")

        for slug in machine.slug_to_state:
            if not isinstance(slug, str):
                raise ValueError(
                    f"The slug {repr(slug)} is invalid. Slugs should be strings."
                )

        self.machine = machine
        kwargs["max_length"] = max(map(len, machine.slug_to_state))
        kwargs.setdefault("verbose_name", machine.label)
        kwargs["choices"] = [
            (state.slug, state.label)
            for state in machine.slug_to_state.values()
        ]
        if "default" in kwargs:
            kwargs["default"] = self.value_to_string(kwargs["default"])
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs["max_length"]
        del kwargs["choices"]
        if kwargs["verbose_name"] == self.machine.label:
            del kwargs["verbose_name"]

        return name, path, (self.machine,), kwargs

    def contribute_to_class(self, cls, name, *args, **kwargs):
        super().contribute_to_class(cls, name, *args, **kwargs)
        self.machine.attr_name = self.attname

    # noinspection PyUnusedLocal
    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        if value is None:
            return value

        if isinstance(value, StateMeta):
            return value

        return self.machine.slug_to_state[value]

    def get_prep_value(self, value):
        machine = self.machine
        if isinstance(value, StateMeta):
            if value not in machine.states:
                raise ValidationError(
                    f"{value} is a state class but isn't one of the states "
                    f"in the machine {machine.__name__}, which are "
                    f"{sorted(machine.states, key=lambda c: c.__name__)}",
                )
            return value.slug
        elif isinstance(value, str):
            if value not in machine.slug_to_state:
                raise ValidationError(
                    f"{value} is not one of the valid slugs for this machine: "
                    f"{sorted(state.slug for state in machine.states)}",
                )
        elif value is not None:
            raise ValidationError(
                f"{self.name} should be a state class, a string, or None",
            )

        return value

    def get_db_prep_value(self, value, connection, prepared=False):
        return self.get_prep_value(value)

    def value_to_string(self, obj):
        return self.get_prep_value(obj)
