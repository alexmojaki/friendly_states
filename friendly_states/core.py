import ast
import functools
import inspect
from abc import ABCMeta, abstractmethod
from typing import Type

from friendly_states.exceptions import IncorrectSummary, InheritedFromState, CannotInferOutputState, \
    DuplicateStateNames, DuplicateOutputStates, UnknownOutputState, ReturnedInvalidState, GetStateDidNotReturnState
from .exceptions import StateChangedElsewhere, IncorrectInitialState, MultipleMachineAncestors
from .utils import snake


class StateMeta(ABCMeta):
    subclasses = None
    name_to_state = None
    slug_to_state = None
    states = None
    direct_transitions = None
    is_complete = False
    machine = None

    def __new__(mcs, name, bases, attrs):
        """
        Called when a new class is declared with this metaclass.
        In particular, called when subclassing BaseState.
        Just keeps track of their machines and their subclasses,
        the real work happens in complete()
        """

        cls: StateMeta = super().__new__(mcs, name, bases, attrs)

        if cls.is_complete:
            raise ValueError(
                "This machine is already complete, you cannot add more subclasses.",
            )

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
        assert issubclass(machine, BaseState)

        cls.machine = machine

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
        """
        Must be called on the machine after all subclasses have been declared.

        Replaces the transitions with wrappers that do the state change magic,
        sets many of the metadata attributes, and checks validity and the summary.
        """

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

        slug_to_state = [(state.slug, state) for state in cls.states]
        cls.slug_to_state = dict(slug_to_state)
        if len(cls.states) != len(cls.slug_to_state):
            raise DuplicateStateNames(
                "Some of the states in this machine have the same slug: {slug_to_state}",
                slug_to_state=sorted(slug_to_state),
            )

        for sub in cls.subclasses:
            transitions = []
            for method_name, func in list(sub.__dict__.items()):
                # Find functions with a return annotation like
                # -> [OutputState, ...]
                if not inspect.isfunction(func):
                    continue

                annotation = func.__annotations__.get("return")
                if not annotation:
                    continue

                output_names = extract_state_names(annotation)
                if not output_names:
                    continue

                transition = sub._make_transition_wrapper(func, output_names)
                transitions.append(transition)

                # Replace the function
                setattr(sub, method_name, transition)

            sub.direct_transitions = frozenset(transitions)

        summary = cls.__dict__.get("Summary")
        if summary:
            cls.check_summary(summary)

        cls.is_complete = True

    def _make_transition_wrapper(cls, func, output_names):
        """
        Returns a function which wraps a transition to replace it.
        The wrapper does the state change after calling the original function.
        """

        if len(set(output_names)) != len(output_names):
            raise DuplicateOutputStates(
                "The transition function {func} in the class {cls} "
                "declares some output states more than once: {output_names}",
                func=func,
                cls=cls,
                output_names=output_names,
            )

        try:
            output_states = frozenset(
                cls.name_to_state[name]
                for name in output_names
            )
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
        def wrapper(self: BaseState, *args, **kwargs):
            result: 'Type[BaseState]' = func(self, *args, **kwargs)
            if result is None:
                # Infer the next state based on the annotation
                if len(output_states) > 1:
                    raise CannotInferOutputState(
                        "This transition {func} has multiple output states {output_states}, "
                        "you must return one.",
                        output_states=sorted(output_states),
                        func=func,
                    )
                (result,) = output_states

            if result not in output_states:
                raise ReturnedInvalidState(
                    "The transition {func} returned {result}, "
                    "which is not in the declared output states {output_states}",
                    output_states=sorted(output_states),
                    func=func,
                    result=result,
                )

            current = self._get_and_check_state(
                StateChangedElsewhere,
                "The state of {obj} has changed to {state} since instantiating {desired}. "
                "Did you change the state inside a transition method? Don't."
            )

            self.set_state(current, result)

        wrapper.output_states = output_states
        return wrapper

    def __repr__(cls):
        if cls.machine:
            return cls.__name__
        return super().__repr__()

    def __lt__(cls, other):
        if not isinstance(other, StateMeta):
            return NotImplemented
        return cls.__name__ < other.__name__

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
        If a state is renamed, this should be set explicitly as a class attribute
        to the original value to avoid data problems.
        """
        return cls.__dict__.get("slug", cls.__name__)

    @property
    def label(cls):
        """
        Display name of state for forms etc.
        """
        result = cls.__dict__.get("label")
        if result is not None:
            return result
        else:
            return snake(cls.slug).replace("_", " ").title()

    @property
    def is_state(cls):
        return cls in (cls.states or ())

    @property
    def transitions(cls):
        return frozenset().union(*[
            getattr(sub, "direct_transitions", ()) or ()
            for sub in cls.__mro__
        ])

    @property
    def output_states(cls):
        """
        Set of states which can be reached directly from this state.
        """
        if not cls.is_state:
            raise AttributeError("This is not a state class")

        return frozenset().union(*[
            getattr(func, "output_states", [])
            for func in cls.transitions
        ])

    def check_summary(cls, graph):
        """
        Checks that the summary graph matches the state classes.
        """
        missing_classes = []
        wrong_outputs = []
        for state_name, annotation in graph.__annotations__.items():
            output_names = extract_state_names(annotation)
            assert output_names is not None
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


class BaseState(metaclass=StateMeta):
    """
    Abstract base class of all states.
    To make state machines you will need a concrete implementation
    with get_state and set_state, usually AttributeState.
    """

    def __init__(self, obj):
        if not type(self).is_complete:
            raise ValueError(
                f"This machine is not complete, call {self.machine.__name__}.complete() "
                f"after declaring all states (subclasses).",
            )

        self.obj = obj
        self._get_and_check_state(
            IncorrectInitialState,
            "{obj} should be in state {desired} but is actually in state {state}"
        )

    def _get_and_check_state(self, exception_class, message_format):
        state = self.get_state()
        if not (isinstance(state, type) and issubclass(state, BaseState)):
            raise GetStateDidNotReturnState(
                f"get_state is supposed to return a subclass of {BaseState.__name__}, "
                "but it returned {returned}",
                returned=state,
            )
        desired = type(self)
        if not issubclass(state, desired):
            raise exception_class(
                message_format,
                obj=self.obj,
                desired=desired,
                state=state,
            )

        return state

    @abstractmethod
    def get_state(self) -> 'Type[BaseState]':
        pass

    @abstractmethod
    def set_state(self, previous_state: 'Type[BaseState]', new_state: 'Type[BaseState]'):
        pass

    def __repr__(self):
        return f"{type(self).__name__}(obj={repr(self.obj)})"


class AttributeState(BaseState):
    """
    A simple base state class which keeps the state in an attribute of the object.
    This is the most common base class for machines.

    By default the attribute is named 'state', this can be overridden with the
    attr_name attribute on this class.
    """

    attr_name = "state"

    def get_state(self):
        return getattr(self.obj, self.attr_name)

    def set_state(self, previous_state, new_state):
        setattr(self.obj, self.attr_name, new_state)


class MappingKeyState(BaseState):
    """
    An alternative base state class which gets/sets the state via square bracket access,
    e.g. obj['state'].

    By default the mapping key is the string 'state', this can be overridden with the
    key_name attribute on this class.
    """
    key_name = "state"

    def get_state(self):
        return self.obj[self.key_name]

    def set_state(self, previous_state, new_state):
        self.obj[self.key_name] = new_state


def extract_state_names(annotation):
    if not isinstance(annotation, str):
        raise ValueError(
            "Found non-string annotation. Remember to add:\n\n"
            "from __future__ import annotations\n\n"
            "at the top of your file."
        )

    try:
        tree = ast.parse(annotation)
    except SyntaxError:
        return None

    if len(tree.body) != 1:
        return None

    lst = tree.body[0].value
    if not isinstance(lst, ast.List):
        return None

    result = []
    for elem in lst.elts:
        if isinstance(elem, ast.Name):
            result.append(elem.id)
        elif isinstance(elem, ast.Attribute):
            result.append(elem.attr)
        else:
            return None

    return result
