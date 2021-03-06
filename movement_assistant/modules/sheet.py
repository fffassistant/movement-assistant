from movement_assistant.classes.botupdate import BotUpdate
import gspread
import os
import json
import pickle
from oauth2client.service_account import ServiceAccountCredentials
from movement_assistant.modules import settings, utils, database
from datetime import datetime

if not (os.path.isfile('movement_assistant/secrets/sheet_token.pkl') and os.path.getsize('movement_assistant/secrets/sheet_token.pkl') > 0):
    # use creds to create a client to interact with the Google Drive API
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/drive.file',
        'https://www.googleapis.com/auth/drive']
    # CREDENTIALS HAVE NOT BEEN INITIALIZED BEFORE
    client_secret = os.environ.get('CLIENT_SECRET')
    if client_secret == None:
        # CODE RUNNING LOCALLY
        print('DATABASE: Resorted to local JSON file')
        with open('movement_assistant/secrets/client_secret.json') as json_file:
            client_secret_dict = json.load(json_file)
    else:
        # CODE RUNNING ON SERVER
        client_secret_dict = json.loads(client_secret)
        print("JSON CLIENT SECRET:  ", type(client_secret_dict))

    creds = ServiceAccountCredentials.from_json_keyfile_dict(
        client_secret_dict, scope)
    pickle.dump(creds, open(
        'movement_assistant/secrets/sheet_token.pkl', 'wb'))

creds = pickle.load(
    open("movement_assistant/secrets/sheet_token.pkl", "rb"))
client = gspread.authorize(creds)

# IF NO SPREADSHEET ENV VARIABLE HAS BEEN SET, SET UP NEW SPREADSHEET
if settings.get_var('SPREADSHEET') == None:
    print("DATABASE: Create new database")
    settings.set_sheet(client)
print("DATABASE: id == ", settings.get_var('SPREADSHEET'))

SPREADSHEET = settings.get_var('SPREADSHEET')
spreadsheet = client.open_by_key(SPREADSHEET)
groupchats = spreadsheet.get_worksheet(0)
calls = spreadsheet.get_worksheet(1)
archive = spreadsheet.get_worksheet(2)
logs = spreadsheet.get_worksheet(3)


def log(timestamp, user_id, action, group_name, item=''):
    print('LOG')
    logs.append_row([timestamp, user_id, action, group_name, item])


def save_group(botupdate):
    # SAVE GROUP IN DATABASE
    group = botupdate.obj
    parent_title = ''
    if group.is_subgroup:
        parent_title = database.get(group.parentgroup)[0].title
    print("SHEET: Saved group | Parent: ", parent_title, ' | Key: ', group.key)
    groupchats.append_row([group.key, group.title, group.category, group.region, group.restriction,
                           group.admin_string, group.platform, parent_title, group.purpose, group.onboarding, str(group.date), group.activator_name])
    # LOG
    log(str(group.date), botupdate.user.id, 'ACTIVATE GROUP', group.title)


def edit_group(botupdate):
    group = botupdate.obj
    old_row = find_row_by_id(item_id=group.key)[0]
    groupchats.delete_row(old_row)
    parent_title = ''
    parent = database.get(group.parentgroup)[0]
    if group.is_subgroup:
        parent_title = parent.title
    print("SHEET: Edited group | Parent: ", parent_title)
    groupchats.append_row([group.key, group.title, group.category, group.region, group.restriction,
                           group.admin_string, group.platform, parent_title, group.purpose, group.onboarding, str(group.date), group.activator_name])
    # LOG
    log(str(group.date), botupdate.user.id, 'EDIT_GROUP', group.title)


def archive_group(chat_id, username):
    print("DATABASE: Archive Group Started")
    group_info = find_row_by_id(chat_id)[0]
    group_info.append(str(utils.now_time()))
    # ADD GROUP INFO TO ARCHIVE
    archive.append_row(group_info)
    # function is not complete


def delete_group(botupdate):
    group = botupdate.obj
    # DELETE CHILDREN LINKS IN DATABASE
    if group.children[0] != None:
        for child in group.children:
            print('DATABASE: delete_group(): Child: ', child)
            row = find_row_by_id(item_id=group.key)[0]
            groupchats.update_cell(row, 8, '')
    print("DATABASE:  Deleted children")

    # REMOVE ROW FROM GROUPS SHEET
    print('SHEET: Group Key: ', group.key)
    try: groupchats.delete_row(find_row_by_id(item_id=group.key)[0])
    except: pass

    # REMOVE CALLS
    for call in group.calls:
        delete_call(BotUpdate(update=botupdate.update, user=botupdate.user, obj=call))

    # LOG
    log(str(utils.now_time()), botupdate.user.id, 'DELETE GROUP', group.title)


def save_call(botupdate):
    # SAVE IN SHEET
    call = botupdate.obj
    calls.append_row([call.key, database.get_group_title(call.chat_id), call.title, str(call.date), str(
        call.time), call.duration_string, call.description, call.agenda_link, call.calendar_url, botupdate.card_url, botupdate.user.name])

    # LOG
    log(str(utils.now_time()), botupdate.update.effective_chat.id, 'NEW CALL',
        database.get_group_title(call.chat_id), call.title)


def delete_call(botupdate: BotUpdate):
    call = botupdate.obj
    call_row = find_row_by_id(sheet=calls, item_id=call.key)[0]
    calls.delete_row(call_row)
    log(str(utils.now_time()), botupdate.user.id, 'DELETE CALL',
        database.get_group_title(call.chat_id), call.title)

    
def edit_call(botupdate):
    call = botupdate.obj
    print('TRELLOC: Key to look for: ', call.key)
    old_row = find_row_by_id(sheet=calls, item_id=call.key)[0]
    print('TRELLOC: Old Row Index: ', old_row)
    calls.delete_row(old_row)
    chat_name = database.get_group_title(call.chat_id)
    calls.append_row([call.key, chat_name, call.title, str(call.date), str(call.time), call.duration_string, call.description, call.agenda_link, call.calendar_url, botupdate.get_card_url(), botupdate.user.name])
    log(str(utils.now_time()), botupdate.update.effective_chat.id, 'EDITED CALL', chat_name, call.title)


def clear_data():
    """
    This method will clear all data in the google spreadsheet. It can be used when testing the program, to easily reset the data when something is broken.
    The data will still remain in the database and the sheet can be repopulated.
    """
    # CLEAR GROUPS SHEET
    rows = get_all_rows(sheet=groupchats)
    for row in rows:
        groupchats.delete_row(row)

    # CLEAR CALLS SHEET
    rows = get_all_rows(sheet=calls)
    for row in rows:
        calls.delete_row(row)

    # CLEAR ARCHIVE SHEET
    rows = get_all_rows(sheet=archive)
    for row in rows:
        archive.delete_row(row)

    # LOG CLEARING
    log(str(utils.now_time()), 'ADMIN', 'CLEAR DATA', '')
    print('SHEET: Erased all data')


def find_row_by_id(sheet=groupchats, item_id="", col=1):
    print("DATABASE: find_row_by_id()")
    if(sheet == "groups"):
        sheet = groupchats
    elif(sheet == "calls"):
        sheet = spreadsheet.worksheet(str(item_id))
        col = 2

    column = sheet.col_values(col)
    rows = []
    for num, cell in enumerate(column):
        if str(cell) == str(item_id):
            rows.append(num + 1)
    if rows == []:
        rows.append(None)
    return rows


def get_all_rows(sheet=groupchats):
    rows = sheet.get_all_values()
    rows_index = []
    for row in rows:
        rows_index.append(rows.index(row) + 1)
    rows_index.pop(0)
    return rows_index
