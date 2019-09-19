import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.transaction import atomic

from friendly_states.core import AttributeState
from friendly_states.django import StateField, DjangoState
from myapp.models import MyModel, Green, Yellow, Red, DefaultableState, NullableState, TrafficLightMachine


def get_lights(counts):
    states = [Green, Yellow, Red]
    result = []
    for count, state in zip(counts, states):
        query = MyModel.objects.filter(state=state)
        assert len(query) == count
        for obj in query:
            assert obj.state is state
        result.append(query)

    return result


@pytest.mark.django_db
def test_light():
    get_lights([0, 0, 0])

    MyModel.objects.create(state=Green)
    MyModel.objects.create(state=Green)
    MyModel.objects.create(state=Red)

    assert len(MyModel.objects.filter(nullable_state=None)) == 3
    assert len(MyModel.objects.filter(defaultable_state=DefaultableState)) == 3

    greens, *_ = get_lights([2, 0, 1])
    obj: MyModel = greens[0]

    assert obj.state is Green
    assert obj.nullable_state is None
    assert obj.defaultable_state is DefaultableState

    obj_id = obj.id
    Green(obj).to_yellow()
    _, yellows, _ = get_lights([1, 1, 1])
    assert yellows[0].id == obj_id

    MyModel.objects.all().delete()
    get_lights([0, 0, 0])

    MyModel.objects.create(state=Green, nullable_state=NullableState)
    (obj,), _, _ = get_lights([1, 0, 0])
    assert obj.nullable_state == NullableState

    with atomic(), pytest.raises(
            ValidationError,
            match=r"NullableState is a state class "
                  r"but isn't one of the states in the machine TrafficLightMachine, "
                  r"which are \[Green, Red, Yellow\]"
    ):
        MyModel.objects.create(state=NullableState)

    with atomic(), pytest.raises(
            ValidationError,
            match="should be a state class, a string, or None"
    ):
        MyModel.objects.create(state=3)

    for options in [
        dict(),
        dict(state=None),
        dict(defaultable_state=None),
    ]:
        with atomic(), pytest.raises(IntegrityError):
            MyModel.objects.create(**options)


def test_deconstruct():
    def check(field_kwargs, deconstructed_kwargs):
        field = StateField(TrafficLightMachine, **field_kwargs)
        *_, args, kwargs = field.deconstruct()
        assert args == (TrafficLightMachine,)
        assert kwargs == deconstructed_kwargs

    check(
        dict(),
        dict(),
    )

    check(
        dict(default=Red),
        dict(default="Red"),
    )

    check(
        dict(verbose_name="STUFF"),
        dict(verbose_name="STUFF"),
    )


def test_not_a_machine():
    with pytest.raises(ValueError):
        StateField(None)

    class NotAMachine(DjangoState):
        pass

    with pytest.raises(
            ValueError,
            match="<class 'tests.test_django.test_not_a_machine.<locals>.NotAMachine'> "
                  "is not a state machine root"
    ):
        StateField(NotAMachine)


def test_not_a_django_state():
    class NotADjangoState(AttributeState):
        is_machine = True

    NotADjangoState.complete()

    with pytest.raises(
            TypeError,
            match="The state machine must be a subclass of DjangoState",
    ):
        StateField(NotADjangoState)


def test_slug_not_a_string():
    class InvalidSlug1(DjangoState):
        is_machine = True

    class S(InvalidSlug1):
        slug = 3

    str(S)

    InvalidSlug1.complete()

    with pytest.raises(
            ValueError,
            match="The slug 3 is invalid. "
                  "Slugs should be strings.",
    ):
        StateField(InvalidSlug1)


def test_invalid_default():
    class Machine(DjangoState):
        is_machine = True

    class S(Machine):
        pass

    str(S)

    Machine.complete()

    with pytest.raises(
            ValidationError,
            match=r"sdf is not one of the valid slugs for this machine: \['S'\]",
    ):
        StateField(Machine, default="sdf")
