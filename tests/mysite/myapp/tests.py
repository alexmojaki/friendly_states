from django.test import TestCase
from myapp.models import MyModel, Green, Yellow, Red


class StatesTestCase(TestCase):
    def setUp(self):
        MyModel.objects.create(state=Green)
        MyModel.objects.create(state=Green)
        MyModel.objects.create(state=Red)

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
        greens, *_ = self.get_lights([2, 0, 1])
        obj = greens[0]
        obj_id = obj.id
        Green(obj).to_yellow()
        _, yellows, _ = self.get_lights([1, 1, 1])
        self.assertEqual(yellows[0].id, obj_id)
