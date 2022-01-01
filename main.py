import os
import pickle
import threading
import time
import uuid

import dateparser
from time import mktime

import discord
from discord.ext.tasks import loop
from discord_slash import SlashCommand, ButtonStyle, ComponentContext
from discord_slash.utils.manage_commands import create_option
from discord_slash.utils.manage_components import create_actionrow, create_button
from flask import request
from flask import Flask

import api_data
import user

client = discord.Client()
slash = SlashCommand(client, sync_commands=True)
guild_ids = [349402004549795840]
mod_users = [343545158140428289]

app = Flask(__name__)

reset_transactions_on_restart = False


@client.event
async def on_ready():
    if not os.path.isdir("users"):
        os.mkdir("users")
    files = os.listdir("users")
    for file in files:
        user.users[int(file)] = pickle.load(open("users/" + file, "rb"))
    if os.path.isfile("api_transactions"):
        api_data.transactions = pickle.load(open("api_transactions", "rb"))
    if os.path.isfile("apps"):
        api_data.apps = pickle.load(open("apps", "rb"))
    if os.path.isfile("vouchers"):
        api_data.vouchers = pickle.load(open("vouchers", "rb"))
    payment_check.start()
    if reset_transactions_on_restart:
        api_data.transactions = {}
        api_data.save_transactions()
    t = threading.Thread(target=app.run)
    t.start()

    print('We have logged in as {0.user}'.format(client))


# Test: echo '{"transaction_id":"ID","token":"fdf06c0d-6a82-11ec-b519-94b86d28e38e"}' | http POST http://127.0.0.1:5000/get_transaction --json
@app.route("/get_transaction", methods=["POST"])
async def api_get_transaction():
    print("t")
    args = request.json
    if args["token"] not in api_data.apps:
        return {"data": "Invalid token!"}, 403
    if args["transaction_id"] not in api_data.transactions:
        return {"message": "No transaction with id " + args["transaction_id"] + "!"}, 400
    transaction = api_data.transactions[args["transaction_id"]]
    return {"data": transaction.__dict__}, 200


def check_arg(args, args_required):
    out = ""
    fail = False
    for i in args:
        if i not in args_required:
            out += i + ", "
            fail = True
    if fail:
        return {"message": "missing required parameters: " + out[:-2]}, 400
    else:
        return False


# Test: echo '{"sender_id":343545158140428289,"receiver_id":518911004164227075,"amount":1,"channel_id":834652900067508255,"token":"fdf06c0d-6a82-11ec-b519-94b86d28e38e"}' | http POST http://127.0.0.1:5000/request_transaction --json
@app.route("/request_transaction", methods=["POST"])
async def api_request_transaction():
    args = request.json
    if args["token"] not in api_data.apps:
        return {"data": "Invalid token!"}, 403
    c_app = api_data.apps[args["token"]]
    transaction_id = str(uuid.uuid1())
    api_data.transactions[transaction_id] = api_data.Transaction(
        transaction_id=transaction_id,
        status=0,
        amount=int(args["amount"]),
        sender_id=int(args["sender_id"]),
        receiver_id=int(args["receiver_id"]),
        time_sent=time.time(),
        time_accepted=None,
        channel_id=int(args["channel_id"]),
        message_sent=False,
        app_name=c_app.name,
    )
    api_data.save_transactions()
    return {"data": api_data.transactions[transaction_id].__dict__}, 200


# Test: echo '{"receiver_id":"343545158140428289","amount":10,"token":"fdf06c0d-6a82-11ec-b519-94b86d28e38e"}' | http POST http://127.0.0.1:5000/add_cc --json
@app.route("/add_cc", methods=["POST"])
async def api_add_cc():
    args = request.json
    if args["token"] not in api_data.apps:
        return {"data": "Invalid token!"}, 403
    c_app = api_data.apps[args["token"]]
    if c_app.withdraw_cap < c_app.withdraw_amount + int(args["amount"]):
        return {"data": "Payment would exceed positive withdraw cap!"}, 403
    if -c_app.withdraw_cap > c_app.withdraw_amount + int(args["amount"]):
        return {"data": "Payment would exceed negative withdraw cap!"}, 403
    receiver_id = int(args["receiver_id"])
    receiver = user.get_user(receiver_id)
    if receiver.coins - int(args["amount"]) < 0:
        return {"data": "Payment would bankrupt user!"}, 403
    receiver.coins += int(args["amount"])
    receiver.save()
    c_app.withdraw_cap += int(args["amount"])
    api_data.save_apps()
    return {"data": "Success!"}, 200


# echo '{"user_id":"343545158140428289","amount":10,"token":"fdf06c0d-6a82-11ec-b519-94b86d28e38e"}' | http POST http://127.0.0.1:5000/voucher/create --json
@app.route("/voucher/create", methods=["POST"])
async def api_create_voucher():
    args = request.json
    if args["token"] not in api_data.apps:
        return {"data": "Invalid token!"}, 403
    c_app = api_data.apps[args["token"]]
    if c_app.withdraw_cap < c_app.withdraw_amount - int(args["amount"]):
        return {"data": "Payment would exceed positive withdraw cap!"}, 403
    if -c_app.withdraw_cap > c_app.withdraw_amount - int(args["amount"]):
        return {"data": "Payment would exceed negative withdraw cap!"}, 403
    if int(args["amount"]) < 0:
        return {"data": "Negative vouchers cannot be created!"}, 403
    voucher_id = str(uuid.uuid1())
    receiver_id = int(args["user_id"])
    receiver = user.get_user(receiver_id)
    if receiver.coins - int(args["amount"]) < 0:
        return {"data": "Payment would bankrupt user!"}, 403
    receiver.coins -= int(args["amount"])
    receiver.save()
    c_app.withdraw_cap -= int(args["amount"])
    api_data.save_apps()
    api_data.vouchers[voucher_id] = api_data.Voucher(
        voucher_id=voucher_id,
        amount=int(args["amount"]),
    )
    api_data.save_vouchers()
    return {"voucher_id": voucher_id}, 200

# echo '{"user_id":"343545158140428289","voucher_id":"a953f378-6aa3-11ec-89ea-94b86d28e38e","token":"fdf06c0d-6a82-11ec-b519-94b86d28e38e"}' | http POST http://127.0.0.1:5000/voucher/redeem --json
@app.route("/voucher/redeem", methods=["POST"])
async def api_redeem_voucher():
    args = request.json
    if args["token"] not in api_data.apps:
        return {"data": "Invalid token!"}, 403
    if args["voucher_id"] not in api_data.vouchers:
        return {"data": "Invalid voucher id!"}, 403
    voucher = api_data.vouchers[args["voucher_id"]]
    c_app = api_data.apps[args["token"]]
    c_user = user.get_user(args["user_id"])
    if c_app.withdraw_cap < c_app.withdraw_amount + voucher.amount:
        return {"data": "Payment would exceed positive withdraw cap!"}, 403
    if -c_app.withdraw_cap > c_app.withdraw_amount + voucher.amount:
        return {"data": "Payment would exceed negative withdraw cap!"}, 403
    c_app.withdraw_cap -= voucher.amount
    api_data.save_apps()
    c_user.coins += voucher.amount
    c_user.save()
    del api_data.vouchers[args["voucher_id"]]
    return {"data": "Success!"}, 200


@loop(seconds=5)
async def payment_check():
    for i in user.users:
        obj = user.get_user(i)
        for payment in obj.current_payments:
            if payment.last_payment is None or abs(time.time() - payment.last_payment) > payment.last_payment:
                sender_discord = await client.fetch_user(obj.discord_id)
                receiver_discord = await client.fetch_user(payment.receiver)
                if payment.amount > obj.coins:
                    await sender_discord.send("You recurring payment to <@" + str(payment.receiver) + "> for " + str(
                        payment.amount) + "cc has been canceled due to a lack of balance in your account!")
                    await receiver_discord.send("<@" + str(obj.discord_id) + ">'s recurring payment to you for " + str(
                        payment.amount) + "cc has been automatically canceled due to a lack of balance in their "
                                          "account!")
                    obj.current_payments.remove(payment)
                else:
                    receiver_obj = user.get_user(payment.receiver)
                    payment.last_payment = time.time()
                    obj.coins -= payment.amount
                    receiver_obj.coins += payment.amount
                    await sender_discord.send("You recurring payment to <@" + str(payment.receiver) + "> for " + str(
                        payment.amount) + "cc has been paid.")
                    await receiver_discord.send("<@" + str(obj.discord_id) + ">'s recurring payment to you for " + str(
                        payment.amount) + "cc has just been paid.")
                    receiver_obj.save()
                obj.save()
    if api_data.transactions_checked < len(api_data.transactions):
        for transaction_id in api_data.transactions:
            transaction = api_data.transactions[transaction_id]
            if not transaction.message_sent:
                buttons = [
                    create_actionrow(create_button(
                        style=ButtonStyle.green,
                        label="Confirm",
                        custom_id="confirm_payment|" + str(transaction.receiver_id) + "|" + str(
                            transaction.amount) + "|" + str(
                            transaction.sender_id) + "|" + transaction.transaction_id
                    )),
                    create_actionrow(create_button(
                        style=ButtonStyle.red,
                        label="Cancel",
                        custom_id="cancel_payment" + "|" + str(transaction.sender_id) + "|" + transaction.transaction_id
                    ))
                ]
                discord_user = await client.fetch_user(transaction.receiver_id)
                channel = await client.fetch_channel(transaction.channel_id)
                await channel.send(
                    "<@" + str(
                        transaction.sender_id) + "> " + transaction.app_name + " is requesting you pay " + discord_user.name + " " + str(
                        transaction.amount) + "cc", components=buttons)
                transaction.message_sent = True
                api_data.save_transactions()


@slash.slash(name="ping", description="Ping-Pong", guild_ids=guild_ids)
async def ping(ctx):  # Defines a new "context" (ctx) command called "ping."
    await ctx.send(f"Pong! ({client.latency * 1000}ms)", hidden=True)


@slash.slash(name="bal",
             description="Gets a users balance",
             options=[
                 create_option(
                     name="username",
                     description="The user to check",
                     option_type=6,
                     required=False
                 )
             ],
             guild_ids=guild_ids)
async def bal(ctx, username=None):
    if username is None:
        username = ctx.author
    c_user = user.get_user(username.id)
    await ctx.send("<@" + str(c_user.discord_id) + "> has " + str(c_user.coins) + "cc", hidden=True)


@slash.slash(name="pay",
             description="Pay another user",
             options=[
                 create_option(
                     name="username",
                     description="The user to pay",
                     option_type=6,
                     required=True
                 ),
                 create_option(
                     name="amount",
                     description="The amount to pay",
                     option_type=4,
                     required=True
                 )
             ],
             guild_ids=guild_ids)
async def pay(ctx, username, amount):
    c_user = user.get_user(username.id)
    buttons = [
        create_actionrow(create_button(
            style=ButtonStyle.green,
            label="Confirm",
            custom_id="confirm_payment|" + str(username.id) + "|" + str(amount) + "|" + str(ctx.author.id) + "|-"
        )),
        create_actionrow(create_button(
            style=ButtonStyle.red,
            label="Cancel",
            custom_id="cancel_payment" + "|" + str(ctx.author.id) + "|-"
        ))
    ]
    discord_user = await client.fetch_user(c_user.discord_id)
    await ctx.send("Pay " + discord_user.name + " " + str(amount) + "cc?", components=buttons)


@client.event
async def on_component(ctx: ComponentContext):
    if ctx.custom_id[0:14] == "cancel_payment":
        if int(ctx.custom_id.split("|")[1]) != ctx.author.id:
            await ctx.send("This is not your confirmation message!", hidden=True)
            return
        channel = await client.fetch_channel(ctx.channel.id)
        init_message = await channel.fetch_message(ctx.origin_message_id)
        await init_message.delete()
        if ctx.custom_id.split("|")[2] != "-":
            api_data.transactions[ctx.custom_id.split("|")[2]].status = 1
            api_data.save_transactions()
    if ctx.custom_id[0:15] == "confirm_payment":
        channel = await client.fetch_channel(ctx.channel.id)
        init_message = await channel.fetch_message(ctx.origin_message_id)
        receiver_id = int(ctx.custom_id.split("|")[1])
        amount = int(ctx.custom_id.split("|")[2])
        receiver_user = user.get_user(receiver_id)
        sender_user = user.get_user(ctx.author.id)
        if int(ctx.custom_id.split("|")[3]) != ctx.author.id:
            await ctx.send("This is not your confirmation message!", hidden=True)
            return
        if sender_user.coins < amount:
            await ctx.send("You don't have enough coins to make that payment!", hidden=True)
            await init_message.delete()
            return
        if 0 > amount:
            await ctx.send("Your payment amount must be more than -1!", hidden=True)
            await init_message.delete()
            return
        receiver_discord = await client.fetch_user(receiver_id)
        receiver_user.coins += amount
        sender_user.coins -= amount
        receiver_user.save()
        sender_user.save()
        if ctx.custom_id.split("|")[2] != "-":
            api_data.transactions[ctx.custom_id.split("|")[4]].status = 2
            api_data.transactions[ctx.custom_id.split("|")[4]].time_accepted = time.time()
            api_data.save_transactions()
        await ctx.send("Done!", hidden=True)
        await init_message.delete()
        await receiver_discord.send("You received " + str(amount) + "cc from <@" + str(sender_user.discord_id) + ">")
    if ctx.custom_id[0:16] == "confirm_rpayment":
        receiver_id = int(ctx.custom_id.split("|")[1])
        amount = int(ctx.custom_id.split("|")[2])
        recurrence = float(ctx.custom_id.split("|")[3])
        channel = await client.fetch_channel(ctx.channel.id)
        init_message = await channel.fetch_message(ctx.origin_message_id)
        if int(ctx.custom_id.split("|")[4]) != ctx.author.id:
            await ctx.send("This is not your confirmation message!", hidden=True)
            return
        if recurrence < 3600:
            await ctx.send("Recurrence cannot be less than 1 hour!", hidden=True)
            return
        if 0 >= amount:
            await ctx.send("Your payment amount must be more than 0!", hidden=True)
            await init_message.delete()
            return
        sender_obj = user.get_user(ctx.author.id)
        sender_obj.current_payments.append(user.Payment(amount, receiver_id, recurrence))
        await ctx.send("Added recurring payment!", hidden=True)
        await init_message.delete()


@slash.slash(name="top",
             description="List everyone and their colacoin in order",
             guild_ids=guild_ids)
async def top(ctx):
    out = "**Shmoney List:**\n"
    sorted_users = user.get_sorted_users()
    for i in sorted_users:
        out += "<@" + str(i) + ">: " + str(user.get_user(i).coins) + "cc\n"
    await ctx.send(out, hidden=True)


@slash.slash(name="recurringpay",
             description="Pay a cc every set time",
             options=[
                 create_option(
                     name="username",
                     description="The user to pay",
                     option_type=6,
                     required=True
                 ),
                 create_option(
                     name="amount",
                     description="The amount to pay",
                     option_type=4,
                     required=True
                 ),
                 create_option(
                     name="recurrence",
                     description="The time interval to pay on",
                     option_type=3,
                     required=True
                 )
             ],
             guild_ids=guild_ids)
async def pay(ctx, username, amount, recurrence):
    c_user = user.get_user(username.id)
    try:
        r = abs(time.time() - mktime(dateparser.parse(recurrence).timetuple()))
    except:
        await ctx.send("Invalid date! Try typing something like \"3 days\"", hidden=True)
        return
    buttons = [
        create_actionrow(create_button(
            style=ButtonStyle.green,
            label="Confirm",
            custom_id="confirm_rpayment|" + str(username.id) + "|" + str(amount) + "|" + str(r) + "|" + str(
                ctx.author.id)
        )),
        create_actionrow(create_button(
            style=ButtonStyle.red,
            label="Cancel",
            custom_id="cancel_payment" + "|" + str(ctx.author.id)
        ))
    ]
    discord_user = await client.fetch_user(c_user.discord_id)
    await ctx.send("Pay " + discord_user.name + " " + str(amount) + "cc every " + str(round(r / 86400, 2)) + " days?",
                   components=buttons)


@slash.slash(name="listpayments",
             description="List recurring payments",
             options=[
                 create_option(
                     name="username",
                     description="The user to check",
                     option_type=6,
                     required=False
                 )
             ],
             guild_ids=guild_ids)
async def list_payments(ctx, username=None):
    if username is None:
        username = ctx.author
    c_user = user.get_user(username.id)
    if len(c_user.current_payments) < 1:
        await ctx.send("<@" + str(username.id) + "> has no recurring payments!", hidden=True)
        return
    out = "**Payments from <@" + str(username.id) + ">:**\n"
    index = 1
    for payment in c_user.current_payments:
        out += str(index) + ". " + str(payment.amount) + "cc to <@" + str(payment.receiver) + "> every " + str(
            round(payment.recurrence / 86400, 2)) + " days.\n"
        index += 1
    await ctx.send(out, hidden=True)


@slash.slash(name="cancelpayment",
             description="Cancel a specified payment",
             options=[
                 create_option(
                     name="cancel_index",
                     description="The user to check",
                     option_type=4,
                     required=True
                 )
             ],
             guild_ids=guild_ids)
async def list_payments(ctx, cancel_index):
    user_obj = user.get_user(ctx.author.id)
    if cancel_index > len(user_obj.current_payments) or cancel_index < 1:
        await ctx.send("That index does not exist! Use /listpayments to see the index's", hidden=True)
        return
    payment = user_obj.current_payments[cancel_index - 1]
    receiver_discord = await client.fetch_user(payment.receiver)
    await receiver_discord.send(
        "<@" + str(ctx.author.id) + "> has canceled their recurring payment of " + str(payment.amount) + "cc to you!")
    user_obj.current_payments.pop(cancel_index - 1)
    user_obj.save()
    await ctx.send("Canceled payment!", hidden=True)


@slash.slash(name="income",
             description="View your income",
             options=[
                 create_option(
                     name="username",
                     description="The user to check",
                     option_type=6,
                     required=False
                 )
             ],
             guild_ids=guild_ids)
async def list_payments(ctx, username=None):
    if username is None:
        username = ctx.author
    c_user = user.get_user(username.id)
    out = 0
    for i_user in user.users:
        for payment in user.users[i_user].current_payments:
            if payment.receiver == c_user.discord_id:
                out += payment.amount / payment.recurrence * 86400
    for payment in c_user.current_payments:
        out -= payment.amount / payment.recurrence * 86400
    await ctx.send("<@" + str(username.id) + ">'s income: " + str(round(out, 2)) + "cc/day", hidden=True)


@slash.slash(name="mod_give_money",
             description="Give money to someone using moderator powers.",
             options=[
                 create_option(
                     name="username",
                     description="The user",
                     option_type=6,
                     required=True
                 ),
                 create_option(
                     name="amount",
                     description="The amount to give",
                     option_type=4,
                     required=True
                 )
             ],
             guild_ids=guild_ids)
async def mod_give_money(ctx, username, amount):
    if ctx.author.id not in mod_users:
        await ctx.send("Added " + str(amount) + "cc to... Wait, hold on!", hidden=True)
        return
    c_user = user.get_user(username.id)
    c_user.coins += amount
    c_user.save()
    await ctx.send("Added " + str(amount) + "cc to <@" + str(username.id) + ">'s balance!", hidden=True)
    return


@slash.slash(name="mod_set_money",
             description="Set money of someone using moderator powers.",
             options=[
                 create_option(
                     name="username",
                     description="The user",
                     option_type=6,
                     required=True
                 ),
                 create_option(
                     name="amount",
                     description="The amount to set",
                     option_type=4,
                     required=True
                 )
             ],
             guild_ids=guild_ids)
async def mod_set_money(ctx, username, amount):
    if ctx.author.id not in mod_users:
        await ctx.send("Set <@" + str(username.id) + ">'s bala... Wait, hold on!", hidden=True)
        return
    c_user = user.get_user(username.id)
    c_user.coins = amount
    c_user.save()
    await ctx.send("Set <@" + str(username.id) + ">'s balance to be " + str(amount) + "cc", hidden=True)
    return


@slash.slash(name="total",
             description="Get the total money in circulation",
             guild_ids=guild_ids)
async def total(ctx):
    num = 0
    for i in user.users:
        num += user.get_user(i).coins
    await ctx.send("There is currently " + str(num) + "cc in circulation", hidden=True)


@slash.slash(name="register_app",
             description="Register an app for the ColaCoin API",
             options=[
                 create_option(
                     name="app_name",
                     description="The display name of your app",
                     option_type=3,
                     required=True
                 )
             ],
             guild_ids=guild_ids)
async def register_app(ctx, app_name):
    token = str(uuid.uuid1())
    api_data.apps[token] = api_data.ApiApp(
        name=app_name,
        owner_id=ctx.author.id,
        rate_limited=False,
        withdraw_cap=0,
        withdraw_amount=0,
        token=token,
    )
    api_data.save_apps()
    await ctx.send("Created app **" + app_name + "**! Use /my_apps to get the key", hidden=True)


@slash.slash(name="my_apps",
             description="Get app tokens",
             guild_ids=guild_ids)
async def my_apps(ctx):
    out_apps = []
    out = "**Apps:**\n"
    for i in api_data.apps:
        if api_data.apps[i].owner_id == ctx.author.id:
            out_apps.append(api_data.apps[i])
    if len(out_apps) < 1:
        await ctx.send("You have no apps! Use /register_app to register an app", hidden=True)
        return
    for i in out_apps:
        out += i.name + ": ||" + str(i.token) + "||\n"
    await ctx.send(out, hidden=True)


@slash.slash(name="mod_set_withdraw_cap",
             description="A",
             options=[
                 create_option(
                     name="app_token",
                     description="The token of the app",
                     option_type=3,
                     required=True
                 ),
                 create_option(
                     name="amount",
                     description="The cap",
                     option_type=4,
                     required=True
                 )
             ],
             guild_ids=guild_ids)
async def set_withdraw_cap(ctx, app_token, amount):
    if ctx.author.id not in mod_users:
        await ctx.send("grrrr", hidden=True)
        return
    if app_token not in api_data.apps:
        await ctx.send("Unknown token!", hidden=True)
        return
    c_app = api_data.apps[app_token]
    c_app.withdraw_cap = amount
    api_data.save_apps()
    await ctx.send("Updated limit", hidden=True)


client.run(open("token.txt", "r").read())
