from django.db import IntegrityError
from django.db.transaction import atomic
from django.test import TestCase

from friendly_states.django import StateField
from myapp.models import MyModel, Green, Yellow, Red, DefaultableState, NullableState, TrafficLightMachine


class StatesTestCase(TestCase):
    def get_lights(self, counts):
        states = [Green, Yellow, Red]
        result = []
        for count, state in zip(counts, states):
            query = MyModel.objects.filter(state=state)
            self.assertEqual(len(query), count)
            for obj in query:
                self.assertIs(obj.state, state)
            result.append(query)

        return result

    def test_light(self):
        self.get_lights([0, 0, 0])

        MyModel.objects.create(state=Green)
        MyModel.objects.create(state=Green)
        MyModel.objects.create(state=Red)

        self.assertEqual(len(MyModel.objects.filter(nullable_state=None)), 3)
        self.assertEqual(len(MyModel.objects.filter(defaultable_state=DefaultableState)), 3)

        greens, *_ = self.get_lights([2, 0, 1])
        obj: MyModel = greens[0]

        self.assertIs(obj.state, Green)
        self.assertIs(obj.nullable_state, None)
        self.assertIs(obj.defaultable_state, DefaultableState)

        obj_id = obj.id
        Green(obj).to_yellow()
        _, yellows, _ = self.get_lights([1, 1, 1])
        self.assertEqual(yellows[0].id, obj_id)

        MyModel.objects.all().delete()
        self.get_lights([0, 0, 0])

        MyModel.objects.create(state=Green, nullable_state=NullableState)
        (obj,), _, _ = self.get_lights([1, 0, 0])
        self.assertEqual(obj.nullable_state, NullableState)

        for options in [
            dict(),
            dict(state=None),
            dict(defaultable_state=None),
        ]:
            with atomic():
                with self.assertRaises(IntegrityError):
                    MyModel.objects.create(**options)

    def test_deconstruct(self):
        def check(field_kwargs, deconstructed_kwargs):
            field = StateField(TrafficLightMachine, **field_kwargs)
            *_, args, kwargs = field.deconstruct()
            self.assertEqual(args, (TrafficLightMachine,))
            self.assertEqual(kwargs, deconstructed_kwargs)

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
