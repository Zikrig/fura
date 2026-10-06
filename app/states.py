from maxapi.context.state_machine import State, StatesGroup


class StaffAdd(StatesGroup):
    link = State()
    name = State()
    settlement = State()


class StaffEdit(StatesGroup):
    value = State()
    settlements = State()


class SettlementFlow(StatesGroup):
    name = State()


class VehicleFlow(StatesGroup):
    name = State()


class PriceFlow(StatesGroup):
    waiting_file = State()
    amount = State()


class EntryFlow(StatesGroup):
    photo = State()
    vehicle = State()
    settlement = State()
    plot = State()


class ResultsFlow(StatesGroup):
    date = State()
    range = State()
