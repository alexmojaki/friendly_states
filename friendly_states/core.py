import functools
import inspect
import re
from abc import ABCMeta, abstractmethod
from typing import Type

from littleutils import only

from friendly_states.exceptions import IncorrectSummary, InheritedFromState, CannotInferOutputState, \
    DuplicateStateNames, DuplicateOutputStates, UnknownOutputState, ReturnedInvalidState, GetStateDidNotReturnState
from .exceptions import StateChangedElsewhere, IncorrectInitialState, MultipleMachineAncestors
from .utils import snake


class StateMeta(ABCMeta):
    subclasses = None
    name_to_state = None
    states = None
    direct_transitions = None

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
            if isinstance(ancestor, StateMeta)
            if ancestor.is_machine
        ]

        if not machine_classes:
            # This is not part of any machine
            return cls

        if len(machine_classes) > 1:
            raise MultipleMachineAncestors(
                "Multiple machine classes found in ancestors of {cls}: {machine_classes}",
                cls=cls,
                machine_classes=machine_classes,
            )

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
            if not ancestor.is_abstract:
                raise InheritedFromState(
                    "{cls} inherits from {ancestor} and both are part of the machine {machine}, "
                    "but {ancestor} is not abstract. If it should be, mark it with is_abstract = True. "
                    "You cannot inherit from actual state classes.",
                    cls=cls,
                    ancestor=ancestor,
                    machine=machine,
                )

        machine.subclasses.add(cls)

        return cls

    def complete(cls):
        if not cls.is_machine:
            raise ValueError(
                "complete() can only be called on state machine roots, i.e. "
                "classes marked with is_machine = True.",
            )

        cls.states = frozenset(
            sub for sub in cls.subclasses
            if not sub.is_abstract
        )
        cls.name_to_state = {state.__name__: state for state in cls.states}
        if len(cls.states) != len(cls.name_to_state):
            raise DuplicateStateNames(
                "Some of the states {states} in this machine have the same name.",
                states=cls.states,
            )

        for sub in cls.subclasses:
            transitions = []
            for method_name, func in list(sub.__dict__.items()):
                # Find functions with a return annotation like
                # -> [OutputState, ...]
                if not inspect.isfunction(func):
                    continue

                annotation = func.__annotations__.get("return")
                if not (annotation and annotation[0] == "[" and annotation[-1] == "]"):
                    continue

                output_names = re.findall(r"\w+", annotation)
                if not output_names:
                    continue

                transition = sub._make_transition_wrapper(func, output_names)
                transitions.append(transition)

                # Replace the function
                setattr(sub, method_name, transition)

            sub.direct_transitions = tuple(transitions)

        summary = cls.__dict__.get("Summary")
        if summary:
            cls.check_graph(summary)

    def _make_transition_wrapper(cls, func, output_names):
        if len(set(output_names)) != len(output_names):
            raise DuplicateOutputStates(
                "The transition function {func} in the class {cls} "
                "declares some output states more than once: {output_names}",
                func=func,
                cls=cls,
                output_names=output_names,
            )

        try:
            output_states = {
                cls.name_to_state[name]
                for name in output_names
            }
        except KeyError as e:
            raise UnknownOutputState(
                "The transition function {func} in the class {cls} "
                "declares an output state {name} which doesn't exist "
                "in the state machine. The available states are {states}. "
                "Did you forget to inherit from the machine?",
                func=func,
                cls=cls,
                states=cls.states,
                name=e.args[0],
            ) from e

        @functools.wraps(func)
        def wrapper(self: AbstractState, *args, **kwargs):
            result: 'Type[AbstractState]' = func(self, *args, **kwargs)
            if result is None:
                # Infer the next state based on the annotation
                if len(output_states) > 1:
                    raise CannotInferOutputState(
                        "This transition {func} has multiple output states {output_states}, "
                        "you must return one.",
                        output_states=output_states,
                        func=func,
                    )
                result = only(output_states)

            if result not in output_states:
                raise ReturnedInvalidState(
                    "The transition {func} returned {result}, "
                    "which is not in the declared output states {output_states}",
                    output_states=output_states,
                    func=func,
                    result=result,
                )

            current = self._get_and_check_state(
                StateChangedElsewhere,
                "The state of {instance} has changed to {state} since instantiating {desired}. "
                "Did you change the state inside a transition method? Don't."
            )

            self.set_state(current, result)

        wrapper.output_states = output_states
        return wrapper

    def __repr__(cls):
        if cls.is_state:
            return cls.__name__
        return super().__repr__()

    @property
    def is_machine(cls):
        return cls.__dict__.get("is_machine", False)

    @property
    def is_abstract(cls):
        return cls.__dict__.get("is_abstract", False)

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
    def transitions(cls):
        return set().union(*[
            getattr(sub, "direct_transitions", ()) or ()
            for sub in cls.__mro__
        ])

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
            for func in cls.transitions
        ])

    def check_graph(cls, graph):
        """
        Checks that the summary graph matches the state classes.
        """
        missing_classes = []
        wrong_outputs = []
        for state_name, annotation in graph.__annotations__.items():
            output_names = re.findall(r"\w+", annotation)
            state = cls.name_to_state.get(state_name)
            if state:
                actual_output_names = {
                    out.__name__
                    for out in state.output_states
                }
                if set(output_names) != actual_output_names:
                    wrong_outputs.append((state, output_names, actual_output_names))
            else:
                missing_classes.append((state_name, output_names))

        if not (missing_classes or wrong_outputs):
            return

        message = "\n"

        if missing_classes:
            message += "Missing states:"
            for state_name, output_names in missing_classes:
                message += f"\n\nclass {state_name}({cls.__name__}):"
                if output_names:
                    for output in output_names:
                        message += f"""
    def to_{snake(output)}(self) -> [{output}]:
        pass\n"""
                else:
                    message += "\n    pass\n\n\n"

        if wrong_outputs:
            message += "Wrong outputs:\n\n"
            for state, output_names, actual_output_names in wrong_outputs:
                message += f"Outputs of {state.__name__}:\n"
                message += f"According to summary       : {', '.join(sorted(output_names))}\n"
                message += f"According to actual classes: {', '.join(sorted(actual_output_names))}\n\n"

        raise IncorrectSummary(message)


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
        self._get_and_check_state(
            IncorrectInitialState,
            "{instance} should be in state {desired} but is actually in state {state}"
        )

    def _get_and_check_state(self, exception_class, message_format):
        state = self.get_state()
        if not (isinstance(state, type) and issubclass(state, AbstractState)):
            raise GetStateDidNotReturnState(
                f"get_state is supposed to return a subclass of {AbstractState.__name__}, "
                "but it returned {current}",
                returned=state,
            )
        desired = type(self)
        if state is not desired:
            raise exception_class(
                message_format,
                instance=self.inst,
                desired=desired,
                state=state,
            )

        return state

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
