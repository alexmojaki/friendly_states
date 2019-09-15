import functools
import inspect
import re

from django.db import models
from littleutils import only

from .utils import snake


class StateMeta(type):
    name_to_state = {}
    slug_to_state = {}
    states_set = set()

    def __new__(mcs, name, bases, attrs):
        """
        Called when a new class is declared with this metaclass.
        In particular, called when a state is created by subclassing State.

        Replaces each transition function with a wrapper that actually changes the state.
        """

        cls: StateMeta = super().__new__(mcs, name, bases, attrs)

        machine_classes = [
            ancestor
            for ancestor in cls.__mro__
            if ancestor.__dict__.get("is_machine")
        ]

        if not machine_classes:
            # This is not part of any machine
            return cls

        if len(machine_classes) > 1:
            raise ValueError(f"Multiple machine classes found in ancestors of {cls}: {machine_classes}")

        machine: StateMeta = machine_classes[0]

        # This class is a machine root
        # It gets fresh collections for its states
        if cls is machine:
            cls.name_to_state = {}
            cls.slug_to_state = {}
            cls.states_set = set()
            return cls

        # Check that abstract classes have been declared correctly
        for ancestor in cls.__mro__[1:]:
            if ancestor is machine:
                break
            if machine not in ancestor.__mro__:
                # This ancestor is unrelated to state machines
                continue
            if not ancestor.__dict__.get("is_abstract"):
                raise ValueError(f"{cls} inherits from {ancestor} and both are part of the machine {machine}, "
                                 f"but {ancestor} is not abstract. If it should be, mark it with is_abstract = True. "
                                 f"You cannot inherit from actual state classes.")

        for method_name, func in list(cls.__dict__.items()):
            # Find functions with a return annotation like
            # -> [OutputState, ...]
            if not inspect.isfunction(func):
                continue

            annotation = func.__annotations__.get("return")
            if not (annotation and annotation[0] == "[" and annotation[-1] == "]"):
                continue

            # Replace the function
            setattr(cls, method_name, cls.make_transition_wrapper(func, annotation))

        if cls.__dict__.get("is_abstract"):
            return cls

        # This class is an actual concrete state!
        # Add class to various useful collections in the machine
        machine.name_to_state[name] = cls
        machine.slug_to_state[cls.slug] = cls
        machine.states_set.add(cls)

        return cls

    def make_transition_wrapper(cls, func, annotation):
        output_names = re.findall(r"\w+", annotation)
        assert len(output_names) >= 1

        @functools.wraps(func)
        def wrapper(self: State, *args, **kwargs):
            result: StateMeta = func(self, *args, **kwargs)
            if result is None:
                # Infer the next state based on the annotation
                if len(output_names) > 1:
                    raise ValueError(f"This transition has multiple output states {output_names}, you must return one")
                result = cls.name_to_state[only(output_names)]
            assert result in cls.states_set

            # Ensure the next state is listed in the annotation
            assert result.__name__ in output_names

            # Do the state change
            self.transition(result)

        wrapper.output_names = output_names
        return wrapper

    @property
    def slug(cls):
        """
        The state in string form so that it can be stored in databases etc.
        If a state (a State subclass) is renamed, this should be set explicitly as a class attribute
        to the original value to avoid data problems.
        """
        return cls.__name__

    @property
    def label(self):
        """
        Display name of state for forms etc.
        """
        return snake(self.slug).replace("_", " ").title()

    @property
    def slug_label(self):
        """
        Minor convenience for constructing lists of choices for Django.
        """
        return self.slug, self.label

    @property
    def output_states(cls):
        """
        Set of states (State subclasses) which can be reached directly from this state.
        :return:
        """
        return set().union(*[
            [
                cls.name_to_state[name]
                for name in getattr(func, "output_names", [])
            ]
            for func in cls.__dict__.values()  # TODO doesn't handle inheritance of state classes
        ])

    def generate_classes(cls, graph):
        """
        Generates Python source code with stubs of state classes
        from a summary graph.
        """
        for name, annotation in graph.__annotations__.items():
            if name in cls.name_to_state:
                continue
            print(f"class {name}(State):")
            output_names = re.findall(r"\w+", annotation)
            if output_names:
                for output in output_names:
                    print(f"""
        def (self) -> [{output}]:
            pass
    """)
            else:
                print("    pass\n")

    def check_graph(cls, graph):
        """
        Checks that the summary graph matches the state classes.
        """
        for name, annotation in graph.__annotations__.items():
            output_names = re.findall(r"\w+", annotation)
            output_states = {
                cls.name_to_state[output_name]
                for output_name in output_names
            }
            state = cls.name_to_state[name]
            assert state.output_states == output_states


class State(metaclass=StateMeta):
    """
    Base class of all states.

    To create a state:

     - Subclass this class.
     - Give it methods to declare transitions to other states.
     - Add a return annotation with a list of possible output states to those methods.
     - If a transition method has several possible output states, it must return one of them.

    Example:

        class MyState(State):
            def do_thing(self) -> [NextState]:
                pass

            def other_thing(self, option) -> [NextState, OtherState]
                if option:
                    return NextState
                else:
                    return OtherState

    Doing a transition then looks like this:

        MyState(case).do_thing()

    MyState(case) will assert that the case is in fact in the state MyState.
    After do_thing() succeeds, transition() will be called which updates the state in the DB.
    """

    state_attribute_name = "state"

    def __init__(self, inst):
        self.inst = inst
        if self.state is not type(self):
            raise ValueError(f"{self.inst} is in state {self.state}, not {type(self)}")

    def transition(self, next_state):
        self.state = next_state

    @property
    def state(self):
        return getattr(self.inst, self.state_attribute_name)

    @state.setter
    def state(self, next_state):
        setattr(self.inst, self.state_attribute_name, next_state)


class DjangoState(State):
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

    def transition(self, next_state):
        field = only(
            f for f in type(self.inst)._meta.get_fields()
            if hasattr(f, "_state_machine_class")
            if isinstance(self, f._state_machine_class)
        )
        setattr(self.inst, field.attname, next_state.slug)
        self.inst.save()
