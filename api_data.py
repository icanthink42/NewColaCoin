import pickle

transactions = {}
transactions_checked = 0
apps = {}
vouchers = {}


def save_transactions():
    pickle.dump(transactions, open("api_transactions", "wb"))


def save_apps():
    pickle.dump(apps, open("apps", "wb"))


def save_vouchers():
    pickle.dump(vouchers, open("vouchers", "wb"))


class Transaction:
    def __init__(self, transaction_id, status, amount, sender_id, receiver_id, time_sent, time_accepted, channel_id,
                 message_sent, app_name):
        self.transaction_id = transaction_id
        self.status = status
        self.amount = amount
        self.sender_id = sender_id
        self.receiver_id = receiver_id
        self.time_sent = time_sent
        self.time_accepted = time_accepted
        self.channel_id = channel_id
        self.message_sent = message_sent
        self.app_name = app_name


class ApiApp:
    def __init__(self, name, owner_id, rate_limited, withdraw_cap, withdraw_amount, token):
        self.name = name
        self.owner_id = owner_id
        self.rate_limited = rate_limited
        self.remove_rate_limit_time = None
        self.withdraw_cap = withdraw_cap
        self.withdraw_amount = withdraw_amount
        self.token = token


class Voucher:
    def __init__(self, voucher_id, amount):
        self.voucher_id = voucher_id
        self.amount = amount
