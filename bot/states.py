from aiogram.fsm.state import State, StatesGroup


class GmailAuthStates(StatesGroup):
    email_input = State()
    password_input = State()
    csv_upload = State()


class TargetListStates(StatesGroup):
    entering_list_name = State()
    # After naming: choose add method (single email vs CSV)
    choosing_add_method = State()
    entering_single_email = State()
    uploading_csv = State()


class OperationStates(StatesGroup):
    selecting_target_list = State()
    selecting_senders = State()      # multi-select via toggle keyboard
    entering_subject = State()
    entering_body = State()
    choosing_delay = State()         # preset or custom
    entering_custom_delay = State()  # e.g. "45 200"
    confirming = State()
