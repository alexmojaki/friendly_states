class StateMachineException(Exception):
    def __init__(self, message_format, **kwargs):
        self.message = message_format.format(**kwargs)
        self.__dict__.update(**kwargs)

    def __str__(self):
        return self.message


class IncorrectInitialState(StateMachineException):
    pass


class StateChangedElsewhere(StateMachineException):
    pass


class MultipleMachineAncestors(StateMachineException):
    pass


class IncorrectSummary(Exception):
    pass
