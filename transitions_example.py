"""
This is the equivalent of the first example in the docs for the 'transitions' library:

https://github.com/pytransitions/transitions#quickstart
"""

from __future__ import annotations
import random
from typing import Type

from friendly_states import AttributeState
from friendly_states.exceptions import IncorrectInitialState


class SuperheroMachine(AttributeState):
    is_machine = True

    class Summary:
        Asleep: [SavingTheWorld, Asleep, HangingOut]
        HangingOut: [SavingTheWorld, Asleep, Hungry]
        Hungry: [SavingTheWorld, Asleep, HangingOut]
        Sweaty: [SavingTheWorld, Asleep, HangingOut]
        SavingTheWorld: [SavingTheWorld, Asleep, Sweaty]


class SuperHeroState(SuperheroMachine):
    is_abstract = True

    def distress_call(self) -> [SavingTheWorld]:
        print("Beauty, eh?")

    def nap(self) -> [Asleep]:
        pass


class Asleep(SuperHeroState):
    def wake_up(self) -> [HangingOut]:
        pass


class HangingOut(SuperHeroState):
    def work_out(self) -> [Hungry]:
        pass


class Hungry(SuperHeroState):
    def eat(self) -> [HangingOut]:
        pass


class Sweaty(SuperHeroState):
    def clean_up(self) -> [Asleep, HangingOut]:
        if random.random() < 0.5:
            return Asleep
        else:
            return HangingOut


class SavingTheWorld(SuperHeroState):
    def complete_mission(self) -> [Sweaty]:
        """ Dear Diary, today I saved Mr. Whiskers. Again. """
        self.obj.kittens_rescued += 1


SuperheroMachine.complete()


class NarcolepticSuperhero(object):
    def __init__(self, name):
        self.name = name
        self.kittens_rescued = 0
        self.state: Type[SuperHeroState] = Asleep


batman = NarcolepticSuperhero("Batman")
Asleep(batman).wake_up()
HangingOut(batman).nap()

try:
    # Any decent IDE/linter will give a warning here
    Asleep(batman).clean_up()
except AttributeError as e:
    print(e)

try:
    # Not possible because batman is asleep
    Sweaty(batman).clean_up()
except IncorrectInitialState as e:
    print(e)

Asleep(batman).wake_up()
HangingOut(batman).work_out()
assert batman.kittens_rescued == 0

# We can use an abstract state for common transitions
# when we don't know the exact current state
SuperHeroState(batman).distress_call()

SavingTheWorld(batman).complete_mission()
assert batman.kittens_rescued == 1

Sweaty(batman).clean_up()
assert batman.state in [HangingOut, Asleep]
