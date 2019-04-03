#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import json
import datetime
import WildermuthVertretungsplan
from functools import wraps

from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

CREDENTIALS_FILE = 'credentials.json'   # stores the credentials for moodle
BOT_TOKEN_FILE = 'bot_token.json'       # stores bot token
USERS_DB_FILE = 'users_db.json'         # stores the registered users


def create_vertretungsplan_obj():
    """read moodle credentials from file and create Vertretungsplan object"""
    with open(CREDENTIALS_FILE) as infile:
        cr = json.load(infile)
        return WildermuthVertretungsplan.WildermuthVertretungsplan(user=cr['user'], password=cr['password'])


def get_user_db():
    """read database from file"""
    try:
        with open(USERS_DB_FILE) as infile:
            return json.load(infile)
    except:
        return {}


def write_user_db(db):
    """write database to file"""
    with open(USERS_DB_FILE, 'w') as outfile:
        json.dump(db, outfile)


def restrict_to_enabled_user(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = str(update.effective_user.id)
        db = get_user_db()
        if user_id not in db or not db[user_id]['enabled']:
            update.message.reply_text('Du bist leider noch nicht freigeschaltet.')
            print('Unauthorized access denied for "{} {} [{}]".'.format(update.effective_user.first_name,
                                                                        update.effective_user.last_name,
                                                                        user_id))
            return
        return func(update, context, *args, **kwargs)
    return wrapped


def restrict_to_admin(func):
    @wraps(func)
    def wrapped(update, context, *args, **kwargs):
        user_id = str(update.effective_user.id)
        db = get_user_db()
        if user_id not in db or not db[user_id]['admin']:
            update.message.reply_text('Admin Berechtigung notwendig!')
            print('Unauthorized admin access denied for "{} {} [{}]".'.format(update.effective_user.first_name,
                                                                              update.effective_user.last_name,
                                                                              user_id))
            return
        return func(update, context, *args, **kwargs)
    return wrapped


# Define a few command handlers. These usually take the two arguments bot and
# update. Error handlers also receive the raised TelegramError object in error.
def start_cmd(update, context):
    """Send a message when the command /start is issued."""
    #print("start\nupdate={}\n{}\ncontext={}\n{}".format(repr(update), str(update), repr(context), str(update)))

    db = get_user_db()

    user_id = str(update.effective_user.id)
    send_to_admin = False
    if user_id in db:
        if db[user_id]['enabled']:
            reply_text = 'Du bist bereits registriert und freigeschaltet.'
        else:
            reply_text = 'Du bist bereits registriert. Bitte warte auf die Freischaltung.'
            send_to_admin = True
        if db[user_id]['admin']:
            reply_text += '\nDu bist Administrator.'
    else:
        reply_text = 'Du bist jetzt registriert. Bitte warte auf die Freischaltung.'
        send_to_admin = True
    update.message.reply_text(reply_text)

    # update entry
    entry = db.setdefault(user_id, {})
    entry['first_name'] = update.effective_user.first_name
    entry['last_name'] = update.effective_user.last_name
    entry['start_time'] = str(datetime.datetime.now())
    entry.setdefault('enabled', False)
    entry.setdefault('admin', False)
    entry.setdefault('subscription', [])

    write_user_db(db)

    # send info to all admins
    if send_to_admin:
        reply_text = update.effective_user.first_name + " " + update.effective_user.last_name + " möchte Zugang haben."
        reply_markup = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton('Akzeptieren', callback_data='accept ' + user_id),
                InlineKeyboardButton('Ablehnen', callback_data='decline ' + user_id),
            ]], one_time_keyboard=True)
        for admin_user_id, entry in db.items():
            if entry['admin']:
                context.bot.send_message(chat_id=admin_user_id, text=reply_text, reply_markup=reply_markup)


def help_cmd(update, context):
    """Send a message when the command /help is issued."""
    update.message.reply_text('Sende /start um zu starten.\nSende /get um den aktuellen Vertretungsplan abzuholen.\nSende /add XX um eine Klasse zu abonnieren.\nSende /rem XX um ein Abo zu löschen.')


@restrict_to_enabled_user
def get_cmd(update, context):
    user_id = str(update.effective_user.id)
    v = create_vertretungsplan_obj()
    db = get_user_db()
    result = v.getResult(db[user_id]['subscription'])
    update.message.reply_markdown(result)
    update.message.reply_document(document=open(v.getPdfFile(), 'rb'))


def reply_subscription(update, subscription):
    """reply list of subcribed classes"""
    if len(subscription) == 0:
        update.message.reply_text('Du hast keine Klassen abonniert. Sende /add um Klassen hinzuzufügen.')
    else:
        update.message.reply_text('Du hast folgende Klassen abonniert:\n' + ', '.join(subscription))


def add_subscription_cmd(update, context):
    """add space separated list of classes to subscription"""
    db = get_user_db()
    user_id = str(update.effective_user.id)

    if user_id not in db:
        update.message.reply_text('Du bist leider noch nicht registriert. Sende zuerst /start.')
        return

    # lowercase arguments and merge with existing subscription using a python set
    subscription = set(db[user_id]['subscription'] + list(map(lambda x: x.lower(), context.args)))
    db[user_id]['subscription'] = list(subscription)
    write_user_db(db)

    reply_subscription(update, subscription)


def remove_subscription_cmd(update, context):
    """remove space separated list of classes from subscription"""
    db = get_user_db()
    user_id = str(update.effective_user.id)

    if user_id not in db:
        update.message.reply_text('Du bist leider noch nicht registriert. Sende zuerst /start.')
        return

    # lowercase arguments and remove from existing subscription using a python set
    subscription = set(db[user_id]['subscription']) - set(map(lambda x: x.lower(), context.args))
    db[user_id]['subscription'] = list(subscription)
    write_user_db(db)

    reply_subscription(update, subscription)


def callback_query_handler(update, context):
    cmd_arg = update.callback_query.data.split(' ')
    if len(cmd_arg) == 0:
        print('Empty callback query received')
        return
    if cmd_arg[0] == 'accept':
        if len(cmd_arg) != 2:
            print('Callback cmd "accept" called with invalid argument count: {}'.format(len(cmd_arg)))
            return
        accept_user(update, context, cmd_arg[1])
    elif cmd_arg[0] == 'decline':
        if len(cmd_arg) != 2:
            print('Callback cmd "decline" called with invalid argument count: {}'.format(len(cmd_arg)))
            return
        decline_user(update, context, cmd_arg[1])
    else:
        print('Unknown callback cmd "{}"'.format(update.callback_query.data))


@restrict_to_admin
def accept_user(update, context, user_id):
    db = get_user_db()
    if user_id not in db:
        print('Callback cmd "accept" called with unknown user: {}'.format(user_id))
        return
    db[user_id]['enabled'] = True
    write_user_db(db)

    context.bot.send_message(chat_id=user_id, text='Du bist jetzt freigeschaltet.')


@restrict_to_admin
def decline_user(update, context, user_id):
    db = get_user_db()
    if user_id not in db:
        print('Callback cmd "decline" called with unknown user: {}'.format(user_id))
        return
    db[user_id]['enabled'] = False
    write_user_db(db)

    context.bot.send_message(chat_id=user_id, text='Deine Freischaltung wurde abgelehnt.')


def error(update, context):
    """Log Errors caused by Updates."""
    logger.warning('Update "%s" caused error "%s"', update, context.error)


def daily_job(context):
    """Daily job to retrieve Vertretungsplan"""
    v = create_vertretungsplan_obj()

    db = get_user_db()
    for user_id in db:
        if db[user_id]['enabled']:
            if v.mDate is None:
               result = 'Datum nicht gefunden'
            elif v.mDate != datetime.date.today() + datetime.timedelta(days=1):
               result = 'keinen Vertretungsplan für Morgen gefunden'
            else:
               result = v.getResult(db[user_id]['subscription'])
            context.bot.send_message(chat_id=user_id, text=result, parse_mode=ParseMode.MARKDOWN)
            context.bot.send_document(chat_id=user_id, document=open(v.getPdfFile(), 'rb'))


def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Make sure to set use_context=True to use the new context based callbacks
    # Post version 12 this will no longer be necessary
    with open(BOT_TOKEN_FILE) as infile:
        bot = json.load(infile)
        updater = Updater(bot['token'], use_context=True)

        # Get the dispatcher to register handlers
        dp = updater.dispatcher

        # on different commands - answer in Telegram
        dp.add_handler(CommandHandler("start", start_cmd))
        dp.add_handler(CommandHandler("help", help_cmd))
        dp.add_handler(CommandHandler("get", get_cmd))
        dp.add_handler(CommandHandler("add", add_subscription_cmd, pass_args=True))
        dp.add_handler(CommandHandler("rem", remove_subscription_cmd, pass_args=True))
        dp.add_handler(CallbackQueryHandler(callback_query_handler))

        # Get the job queue
        jq = updater.job_queue

        jq.run_daily(daily_job, datetime.time(22, 10), (0, 1, 2, 3, 6, 4, 5))

        # log all errors
        dp.add_error_handler(error)

        # Start the Bot
        updater.start_polling()

        # Run the bot until you press Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT. This should be used most of the time, since
        # start_polling() is non-blocking and will stop the bot gracefully.
        updater.idle()


if __name__ == '__main__':
    main()
