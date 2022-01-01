import pickle

users = {}


def get_sorted_users():
    return sorted(users, key=lambda x: users[x].coins, reverse=True)


def get_user(discord_id):
    if discord_id not in users:
        users[discord_id] = User(discord_id)
    out = users[discord_id]
    out.save()
    return out


class User:
    def __init__(self, discord_id):
        self.discord_id = discord_id
        self.coins = 1000
        self.current_payments = []

    def save(self):
        pickle.dump(self, open("users/" + str(self.discord_id), "wb"))


class Payment:
    def __init__(self, amount, receiver, recurrence):
        self.amount = amount
        self.recurrence = recurrence
        self.last_payment = None
        self.receiver = receiver
