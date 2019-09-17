import functools
import inspect
import re
from abc import ABCMeta, abstractmethod
from typing import Type

from littleutils import only

from .utils import snake


class StateMeta(ABCMeta):
    subclasses = None
    name_to_state = None
    states = None

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
        assert issubclass(machine, AbstractState)

        # This class is a machine root
        # It gets fresh collections for its states
        if cls is machine:
            cls.subclasses = set()
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

        machine.subclasses.add(cls)

        return cls

    def complete(cls):
        if not cls.__dict__.get("is_machine"):
            raise ValueError(
                "complete() can only be called on state machine roots, i.e. "
                "classes marked with is_machine = True.",
            )

        cls.states = frozenset(
            sub for sub in cls.subclasses
            if not sub.__dict__.get("is_abstract")
        )
        cls.name_to_state = {state.__name__: state for state in cls.states}
        assert len(cls.states) == len(cls.name_to_state)

        for sub in cls.subclasses:
            for method_name, func in list(sub.__dict__.items()):
                # Find functions with a return annotation like
                # -> [OutputState, ...]
                if not inspect.isfunction(func):
                    continue

                annotation = func.__annotations__.get("return")
                if not (annotation and annotation[0] == "[" and annotation[-1] == "]"):
                    continue

                # Replace the function
                setattr(sub, method_name, sub._make_transition_wrapper(func, annotation))

        summary = cls.__dict__.get("Summary")
        if summary:
            cls.check_graph(summary)

    def _make_transition_wrapper(cls, func, annotation):
        output_names = re.findall(r"\w+", annotation)
        assert len(output_names) >= 1
        output_states = {
            cls.name_to_state[name]
            for name in output_names
        }
        assert len(output_states) == len(output_names)

        @functools.wraps(func)
        def wrapper(self: AbstractState, *args, **kwargs):
            result: 'Type[AbstractState]' = func(self, *args, **kwargs)
            if result is None:
                # Infer the next state based on the annotation
                if len(output_states) > 1:
                    raise ValueError(f"This transition has multiple output states {output_names}, you must return one")
                result = only(output_states)

            # Ensure the next state is listed in the annotation
            assert result in output_states

            # Do the state change
            current = self.get_state()
            if current is not type(self):
                raise StateChangedElsewhere(
                    self,
                    f"state has changed to {current} since instantiation. "
                    f"Did you change the state in a transition method?",
                )

            self.set_state(current, result)

        wrapper.output_states = output_states
        return wrapper

    def __repr__(cls):
        if cls.is_state:
            return cls.__name__
        return super().__repr__()

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
    def is_state(cls):
        return cls in (cls.states or ())

    @property
    def output_states(cls):
        """
        Set of states (State subclasses) which can be reached directly from this state.

        Raises an AttributeError if this is not a state class.
        """
        if not cls.is_state:
            raise AttributeError("This is not a state class")

        return set().union(*[
            getattr(func, "output_states", [])
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


class StateMachineException(Exception):
    def __init__(self, state, message):
        self.state = state
        self.message = message

    def __str__(self):
        return f"for {self.state}: {self.message}"


class IncorrectInitialState(StateMachineException):
    pass


class StateChangedElsewhere(StateMachineException):
    pass


class AbstractState(metaclass=StateMeta):
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

    def __init__(self, inst):
        self.inst = inst
        current = self.get_state()
        if not (isinstance(current, type) and issubclass(current, AbstractState)):
            raise ValueError(f"get_instance_state is supposed to return a subclass of {AbstractState.__name__}, "
                             f"but it returned {current}")
        desired = type(self)
        if current is not desired:
            raise IncorrectInitialState(self, f"instance is actually in state {current}")

    @abstractmethod
    def get_state(self) -> 'Type[AbstractState]':
        pass

    @abstractmethod
    def set_state(self, previous_state: 'Type[AbstractState]', new_state: 'Type[AbstractState]'):
        pass

    def __repr__(self):
        return f"{type(self).__name__}(inst={repr(self.inst)})"


class AttributeState(AbstractState):
    attr_name = "state"

    def get_state(self):
        return getattr(self.inst, self.attr_name)

    def set_state(self, previous_state, new_state):
        setattr(self.inst, self.attr_name, new_state)


class MappingKeyState(AbstractState):
    key_name = "state"

    def get_state(self):
        return self.inst[self.key_name]

    def set_state(self, previous_state, new_state):
        self.inst[self.key_name] = new_state
