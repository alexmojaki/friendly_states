"""
`friendly_states` can easily be used out of the box with Django. Basic usage looks like this:

```python
from django.db import models
from friendly_states.django import StateField, DjangoState

class MyMachine(DjangoState):
    is_machine = True

# ...

class MyModel(models.Model):
    state = StateField(MyMachine)
```

`StateField` is a `CharField` that stores the `slug` of the current state in the database while letting you use the actual state class objects in all your code, e.g:

```python
obj = MyModel.objects.create(state=MyState)
assert obj.state is MyState
objects = MyModel.objects.filter(state=MyState)
```

All keyword arguments are passed straight to `CharField`, except for `max_length` and `choices` which are ignored, see below.

`DjangoState` will automatically save your model after state transitions. To disable this, set `auto_save = False` on your machine or state classes.

`StateField` will automatically discover its name in the model and set that `attr_name` on the machine, so you don't need to set it. But as usual, beware that you can't use different attribute names for the same machine. Also note that the name `_state` is used internally by Django so don't use that.

Because the database stores slugs and the slug is the class name by default, if you rename your classes in code and you want existing data to remain valid, you should set the slug to the old class name:

```python
class MyRenamedState(MyMachine):
    slug = "MyState"
    ...
```

Similarly you mustn't delete a state class if you stop using it as long as your database contains objects in that state, or your code will fail when it tries to work with such an object.

`max_length` is automatically set to the maximum length of all the slugs in the machine. If you want to save space in your database, override the slugs to something shorter.

`choices` is constructed from the `slug` and `label` of every state. To customise how states are displayed in forms etc, override the `label` attribute on the class.
"""


from django.core.exceptions import ValidationError
from django.db import models

from friendly_states.core import StateMeta, AttributeState


class DjangoState(AttributeState):
    __doc__ = globals()["__doc__"]

    attr_name = None
    auto_save = True

    def set_state(self, previous_state, new_state):
        super().set_state(previous_state, new_state)
        if self.auto_save:
            self.obj.save()


class StateField(models.CharField):
    __doc__ = globals()["__doc__"]

    empty_strings_allowed = False

    def __init__(self, machine, *args, **kwargs):
        if not (isinstance(machine, StateMeta) and machine.is_machine):
            raise ValueError(f"{machine} is not a state machine root")

        if not issubclass(machine, DjangoState):
            raise TypeError(f"The state machine must be a subclass of DjangoState")

        if not machine.is_complete:
            raise ValueError(
                f"This machine is not complete, call {machine.__name__}.complete() "
                f"after declaring all states (subclasses).",
            )

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
        if name == "_state":
            raise ValueError(
                "_state is an internal attribute used by Django "
                "and should not be the name of a field."
            )
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
                    f"{sorted(machine.states)}",
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
