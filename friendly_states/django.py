from django.db import models
from littleutils import only

from friendly_states.core import StateMeta, AttributeState


class DjangoState(AttributeState):
    @classmethod
    def state_db_field(cls, **kwargs):
        """
        To be used directly inside a Django database model declaration.
        Returns a pair:
         - field: a models.CharField storing a string containing the slug of a state
         - state: a property which looks up the actual state class from the field's string value
             This property is intentionally read only because changing the state
             should be done with transition methods.

        Example usage:

            class MyModel(django.db.models.Model):
                state_slug, state = MyMachine.state_db_field(default=MyInitialState)

        Then later:

            inst = MyModel()
            MyInitialState(inst).do_transition()

        or:

            if inst.state is MyInitialState:
                ...

        or:

            initial_objects = MyModel.objects.filter(state_slug=MyInitialState.slug)

        The name of the second returned value should match state_attribute_name on this class
        (the default is "state").

        All keyword arguments are passed directly to the Django model field.
        """

        max_length = max(map(len, cls.slug_to_state)) * 2
        assert kwargs.setdefault("max_length", max_length) >= max_length
        kwargs.setdefault("verbose_name", "State")
        default = kwargs.get("default")
        if isinstance(default, StateMeta):
            assert issubclass(default, cls)
            kwargs["default"] = default.slug

        field = models.CharField(
            choices=[
                state.slug_label
                for state in cls.slug_to_state.values()
            ],
            **kwargs,
        )

        field._state_machine_class = cls

        @property
        def state(self):
            slug = getattr(self, field.name)
            return cls.slug_to_state.get(slug)

        return field, state

    def set_state(self, previous_state, new_state):
        field = only(
            f for f in type(self.inst)._meta.get_fields()
            if hasattr(f, "_state_machine_class")
            if isinstance(self, f._state_machine_class)
        )
        setattr(self.inst, field.attname, new_state.slug)
        self.inst.save()
