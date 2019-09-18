class StateMachineException(Exception):
    def __init__(self, message_format, **kwargs):
        if kwargs:
            self.message = message_format.format(**kwargs)
        else:
            self.message = message_format
        self.__dict__.update(**kwargs)

    def __str__(self):
        return self.message


class IncorrectInitialState(StateMachineException):
    pass


class StateChangedElsewhere(StateMachineException):
    pass


class MultipleMachineAncestors(StateMachineException):
    pass


class IncorrectSummary(StateMachineException):
    pass
