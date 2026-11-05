from aiogram.fsm.state import State, StatesGroup


class CreateQR(StatesGroup):
    waiting_input = State()
    waiting_choice = State()
