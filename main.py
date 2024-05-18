from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackContext, ConversationHandler, CallbackQueryHandler
from telegram.error import BadRequest

from warnings import filterwarnings
from telegram.warnings import PTBUserWarning

from threading import Thread
from time import sleep

from data_manage import Reader

filterwarnings(action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning)

(EVENT_NAME, EVENT_MAX_MEMBERS, UPLOAD_THEMES, THEME_NAME, TEAM_DESCRIPTION, 
 CONFIRM_THEME, TEAM_NAME, SEND_REQUEST, TEAM_MANAGE, REQUESTS_MANAGE, ANSWER_REQUEST,
 KICK_MEMBER, CONFIRM_KICK, CHANGE_NEEDS, DELETE_TEAM, QUIT_TEAM, DELETE_EVENT) = range(17)


async def start(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Я бот для создания мероприятий и команд.\n\n"
                                    "/themes - просмотр всех тем мероприятия\n"
                                    "/create_team - создать команду\n"
                                    "/join_team - присоединиться к команде\n"
                                    "/my_teams - информация о ваших командах\n"
                                    "/create_event - создать мероприятие\n"
                                    "/delete_event - удалить мероприятие\n")


async def remove_buttons(chat_data: dict) -> int:
    if not chat_data:
        return
    if chat_data["buttons_message"] is None:
        return
    try:
        await chat_data["buttons_message"].edit_reply_markup(reply_markup=None)
    except BadRequest:
        pass
    chat_data["buttons_message"] = None


async def cancel_any(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:

    return ConversationHandler.END


async def create_event(update: Update, context: CallbackContext) -> int:
    await remove_buttons(context.chat_data)
    await update.message.reply_text("Напишите название мероприятия.")

    return EVENT_NAME


async def get_event_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    event_name = update.message.text
    reader = Reader()
    if not reader.is_event_name_unique(event_name):
        await update.message.reply_text("Мероприятие с таким названием уже существует.")
        return EVENT_NAME
    context.user_data["event_name"] = event_name
    reply_keyboard = [[str(row * 5 + col) for col in range(1, 6)] for row in range(4)]
    markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True)

    await update.message.reply_text("Какое максимальное количество участников команды возможно для данного мероприятия?", reply_markup=markup)

    return EVENT_MAX_MEMBERS


async def get_event_max_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    members_amount = update.message.text
    reader = Reader()
    if not reader.is_digit(members_amount):
        await update.message.reply_text("Введите число.")
        return EVENT_MAX_MEMBERS
    context.user_data["members_amount"] = int(members_amount)
    await update.message.reply_text("Отправьте файл-таблицу с расширением .xlsx, содержащий описание тем мероприятия. "
                                    "Прикрепляю шаблон, в котором описаны инструкции по заполнению данного файла. "
                                    "Файл будет проверен, в случае обнаружения ошибок вы сможете отправить файл заново.")
    chat_id = update.message.chat_id
    doc = open('Шаблон.xlsx', 'rb')
    await context.bot.send_document(chat_id, doc)
    return UPLOAD_THEMES


async def get_themes_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    file = update.message.document
    if file.file_name.split(".")[-1] != "xlsx":
        await update.message.reply_text("Неверный формат файла. Отправьте файл заново.")
        return UPLOAD_THEMES
    
    to_download = await context.bot.get_file(file)
    file_name = await to_download.download_to_drive()

    event_name = context.user_data["event_name"]
    max_members = context.user_data["members_amount"]
    org_id = update.message.from_user.id
    alias = update.message.from_user.username
    reader = Reader()
    errors = reader.add_event_theme(event_name=event_name, org_id=org_id, alias=alias, max_members=max_members, file_url=file_name)
    if errors:
        error_msg = ""
        for index, error in enumerate(errors):
            if index >= 5:
                error_msg += f"Ещё ошибок: {len(errors)-5}"
                break
            error_msg += error + "\n\n"
        error_msg += "Исправьте ошибки и отправьте файл заново."
        await update.message.reply_text(error_msg)
        return UPLOAD_THEMES
    
    await update.message.reply_text(f"Создано мероприятие с названием \"{event_name}\" и "
                                    f"максимальным количеством учаснитков в одной команде {max_members}. Темы успешно загружены.")

    return ConversationHandler.END


async def cancel_create_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Создание мероприятия отменено.")

    return ConversationHandler.END


async def list_events(update: Update, context: CallbackContext) -> int:
    await remove_buttons(context.chat_data)
    context.user_data["command"] = update.message.text
    
    reader = Reader()
    events = reader.get_events()

    if len(events) == 0:
        await update.effective_message.reply_text("На данный момент никаких мероприятий нет.")
        return ConversationHandler.END
    
    keyboard = [[InlineKeyboardButton(event['event'][:80], callback_data=event['event_hash'])] for event in events]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.effective_message.reply_text("Выберите мероприятие, в котором хотите принять участие.", reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg
    
    return EVENT_NAME


async def select_event_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "next#":
        context.user_data["slice_start"] += 10
    elif query.data == "back#":
        context.user_data["slice_start"] -= 10
    elif query.data == "return#" or query.data == "return_to_themes#":
        pass
    else:
        context.user_data["event_hash"] = int(query.data)
        context.user_data["slice_start"] = 0
    
    reader = Reader()
    event_hash = context.user_data["event_hash"]
    event_name = reader.get_event_name(event_hash)

    if context.user_data["command"] == "/create_team":
        themes = reader.get_themes_to_create(update.callback_query.from_user.id, event_hash)
        msg_text = "Отображены только незанятые темы. Для просмотра всех тем используйте /themes."
    elif context.user_data["command"] == "/join_team":
        themes = reader.get_themes_to_join(update.callback_query.from_user.id, event_hash)
        msg_text = "Отображены только темы, к командам которых можно присоединиться. Для просмотра всех тем используйте /themes."
    elif context.user_data["command"] == "/themes":
        themes = reader.get_all_themes(event_hash)
        msg_text = "Отображены все темы."

    if themes == 1:
        await query.edit_message_text("Вы уже участвуете в данном мероприятии.", reply_markup=None)
        return ConversationHandler.END

    if themes:
        if context.user_data["slice_start"] >= len(themes):
            context.user_data["slice_start"] -= 10
        context.user_data["slice_start"] = max(0, context.user_data["slice_start"])
        slice_start = context.user_data["slice_start"]
        slice_end = min(len(themes), slice_start+10)
        keyboard = [[InlineKeyboardButton(themes[key]["theme"][:80], callback_data=int(themes[key]["theme_hash"]))] for key in range(slice_start, slice_end)]
        keyboard.append([InlineKeyboardButton("Назад", callback_data="back#"), InlineKeyboardButton("Далее", callback_data="next#")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            msg = await query.edit_message_text(f"Выберите тему мероприятия \"{event_name}\" для просмотра подробной информации.\n\n" + msg_text + 
                                                f"\n\nСтраница {slice_start//10+1}/{(len(themes)-1)//10+1}", reply_markup=reply_markup)
            context.chat_data["buttons_message"] = msg
        except BadRequest:
            pass
    else:
        if context.user_data["command"] == "/create_team":
            msg_text = "Нет тем, в которых можно создать команду. Для просмотра всех тем используйте /themes."
        elif context.user_data["command"] == "/join_team":
            msg_text = "Нет тем, в команды которых вы можете отправить запрос. Для просмотра всех тем используйте /themes."
        elif context.user_data["command"] == "/themes":
            msg_text = "Темы отстутствуют."
        await query.edit_message_text(f"{msg_text}", reply_markup=None)
        return ConversationHandler.END

    return THEME_NAME


async def select_theme_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    theme_hash = int(query.data)
    event_hash = context.user_data["event_hash"]
    context.user_data["theme_hash"] = theme_hash

    reader = Reader()
    theme_info = reader.theme_info(event_hash, theme_hash)

    if not theme_info:
            msg = await query.edit_message_text("Мероприятие удалено.", reply_markup=None)
            return ConversationHandler.END
    
    info_headers = ["Мероприятие: ", "Тема: ", "Заказчик: ", "Максимум команд: ", "Ответственный: ", "Email ответственного: ", "Описание темы: ", 
                    "Предпосылки: ", "Проблема: ", "Ожидаемый результат: "]
    text = ""
    for index, key in enumerate(list(theme_info.keys())):
        if key == 'theme_hash':
            continue
        if (theme_info[key] == None):
            continue
        text += info_headers[index] + str(theme_info[key]) + "\n\n"

    keyboard = [[InlineKeyboardButton("Назад", callback_data="return#"), InlineKeyboardButton("Выбрать эту тему", callback_data="next#")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text(text, reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return CONFIRM_THEME


async def confirm_theme_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]
    theme_hash = context.user_data["theme_hash"]

    if context.user_data["command"] == "/create_team" or query.data == 'jump_to_create#':
        await remove_buttons(context.chat_data)
        reader = Reader()
        proceed = reader.is_create_theme_available(update.callback_query.from_user.id, event_hash, theme_hash)
        if not proceed:
            await update._effective_message.reply_text("К сожалению, вы больше не можете присоединиться "
                                                    "к данной теме.")
            return ConversationHandler.END
        
        await update._effective_message.reply_text("Введите название команды.")

    elif context.user_data["command"] == "/join_team" or query.data == 'jump_to_join#':
        reader = Reader()
        teams = reader.get_teams_to_join(update.callback_query.from_user.id, event_hash, theme_hash)
        await remove_buttons(context.chat_data)

        if teams == 1:
            await update._effective_message.reply_text("Не удалось создать команду. Вы уже участвуете в данном мероприятии.")
            return ConversationHandler.END
        if len(teams) == 0:
            await update._effective_message.reply_text("К сожалению, все команды по данной теме уже заполены.")
            return ConversationHandler.END
        
        keyboard = [[InlineKeyboardButton(team["team_name"][:80], callback_data=int(team["team_hash"]))] for team in teams]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query.data == "back#":
            msg = await query.edit_message_text("Выберите команду для просмотра подробной информации.", reply_markup=reply_markup)
        else:
            msg = await update._effective_message.reply_text("Выберите команду для просмотра подробной информации.", reply_markup=reply_markup)
        context.chat_data["buttons_message"] = msg
    
    return TEAM_NAME


async def get_team_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    event_hash = context.user_data["event_hash"]
    team_name = update.message.text
    context.user_data["team_name"] = team_name

    reader = Reader()
    if not reader.is_team_name_unique(event_hash, team_name):
        await update.message.reply_text("Команда с таким названием уже участвует в данном мероприятии. Введите другое название.")
        return TEAM_NAME
    
    await update.message.reply_text("Опишите, участников с какими умениями ищет ваша команда. "
                                    "Если ищете кого угодно или никого, так и напишите.")

    return TEAM_DESCRIPTION


async def get_team_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    event_hash = context.user_data["event_hash"]
    theme_hash = context.user_data["theme_hash"]
    team_name = context.user_data["team_name"]
    team_description = update.message.text

    reader = Reader()
    event_name = reader.get_event_name(event_hash)
    theme_name = reader.get_theme_name(event_hash, theme_hash)

    if not reader.is_team_name_unique(event_hash, team_name):
        await update.message.reply_text("К сожалению, уже появилась команда с выбранным вами названием. Введите другое название.")
        return TEAM_NAME
    
    proceed = reader.is_create_theme_available(update.message.from_user.id, event_hash, theme_hash)
    if not proceed:
        await update._effective_message.reply_text("К сожалению, вы больше не можете присоединиться "
                                                    "к данной теме.")
        return ConversationHandler.END
    
    reader.add_team(event_hash, theme_hash, team_name, update.message.from_user.id, update.message.from_user.username, team_description)
    await update.message.reply_text(f"Создана команда \"{team_name}\" в мероприятии \"{event_name}\" "
                                    f"По теме \"{theme_name}\".\n\nВ данный момент команда является открытой, и "
                                    "желающие принять участие в мероприятии могут отправлять вам запросы на "
                                    "присоединение к комнде. Чтобы принимать запросы или закрыть команду "
                                    "используйте /my_teams.")

    return ConversationHandler.END


async def cancel_create_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await remove_buttons(context.chat_data)
    await update.message.reply_text("Создание команды отменено.")

    return ConversationHandler.END
    

async def select_team_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]
    team_hash = int(query.data)
    context.user_data["team_hash"] = team_hash

    await remove_buttons(context.chat_data)

    reader = Reader()
    team_name = reader.get_team_name(event_hash, team_hash)
    team_needs = reader.get_team_description(event_hash, team_hash)
    keyboard = [[InlineKeyboardButton("Назад", callback_data="back#"), InlineKeyboardButton("Присоединиться", callback_data="join#")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    msg = await query.edit_message_text(f"Команда \"{team_name}\" ищет:\n\n{team_needs}", reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg
    return SEND_REQUEST


async def send_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]
    team_hash = context.user_data["team_hash"]

    reader = Reader()
    leader_data = reader.add_member_to_team(update.callback_query.from_user.id, update.callback_query.from_user.username, event_hash, team_hash)
    if leader_data == 1:
        await query.edit_message_text("Не удалось присоединиться. Вы уже участвуете в этом мероприятии.", reply_markup=None)
        return ConversationHandler.END
    elif leader_data == 2:
        await query.edit_message_text("Не удалось присоединиться. Команда закрыта или заполнена.", reply_markup=None)
        return ConversationHandler.END
    
    leader_id = leader_data['leader_id']
    leader_alias = leader_data['leader_alias']
    team_name = leader_data['team_name']
    event_name = reader.get_event_name(event_hash)

    try:
        await context.bot.send_message(chat_id=leader_id, text=f"Был отправлен запрос на присоединение к команде \"{team_name}\" "
                                 f"в мероприятии \"{event_name}\" от пользователя @{update.callback_query.from_user.username}. "
                                 f"Чтобы принять или отклонить запрос, используйте /my_teams.")
        
        await query.edit_message_text(f"Лидеру команды \"{team_name}\" @{leader_alias} был отправлен ваш запрос на присоединение. "
                                      "Рекомендуем связаться с лидером для обсуждения вашего участия.", reply_markup=None)
    except Exception:
        await query.edit_message_text(f"Лидеру команды \"{team_name}\" @{leader_alias} был отправлен ваш запрос на присоединение. "
                                      "но уведомить его не удалось. Он может принять или отклонить запрос используя /my_teams. "
                                      "Рекомендуем связаться с лидером для обсуждения вашего участия.", reply_markup=None)
    return ConversationHandler.END
    

async def cancel_join_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Присоединение к команде отменено.")
    await remove_buttons(context.chat_data)

    return ConversationHandler.END


async def list_member_events(update: Update, context: CallbackContext) -> int:
    await remove_buttons(context.chat_data)
    context.user_data["command"] = update.message.text
    
    reader = Reader()
    events = reader.get_member_events(update.message.from_user.id)

    if not events:
        await update.message.reply_text("На данный момент вы не являетесь участником ни одной команды.")
        return ConversationHandler.END
    
    keyboard = [[InlineKeyboardButton(event['event'][:80], callback_data=event['event_hash'])] for event in events]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text("Команду для какого мероприятия вы хотите просмотреть?", reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg
    
    return EVENT_NAME


async def list_team_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "back#":
        event_hash = context.user_data["event_hash"]
    elif query.data == "flip_state#":
        event_hash = context.user_data["event_hash"]
        team_hash = context.user_data['team_hash']
        reader = Reader()
        reader.flip_team_opened(event_hash, team_hash)
    else:
        event_hash = int(query.data)
        context.user_data["event_hash"] = event_hash

    reader = Reader()
    team_info = reader.get_team_info(update.callback_query.from_user.id, event_hash)

    if not team_info:
            msg = await query.edit_message_text("Вы больше не участвуете в этом мероприятии.", reply_markup=None)
            return ConversationHandler.END
    
    context.user_data['team_hash'] = team_info['team_hash']
    
    team_info['event_hash'] = reader.get_event_name(event_hash)
    team_info['theme_hash'] = reader.get_theme_name(event_hash, team_info['theme_hash'])

    max_members = reader.get_max_members(event_hash)
    cur_members = reader.get_current_members(event_hash, team_info['team_hash'])
    team_info['members'] = f"{cur_members}/{max_members}"
    if team_info['team_opened']:
        team_info['team_opened'] = "открыта для запросов"
        flip_team_state = "Закрыть команду"
    else:
        team_info['team_opened'] = "закрыта для запросов"
        flip_team_state = "Открыть команду"
    
    info_headers = ["Мероприятие: ", "Тема: ", "Команда: ", "", "Лидер: @", "Команда ", "Команда ищет: ", "", "Участники "]
    text = ""
    for index, key in enumerate(list(team_info.keys())):
        if key == 'leader_id':
            continue
        if key == 'team_hash':
            continue
        text += info_headers[index] + str(team_info[key]) + "\n\n"

    if team_info['leader_id'] == update.callback_query.from_user.id:
        keyboard = [[InlineKeyboardButton("Принять/отклонить запрос в команду", callback_data="answer#")],
                    [InlineKeyboardButton(flip_team_state, callback_data="flip_state#")],
                    [InlineKeyboardButton("Исключить участника", callback_data="kick#")],
                    [InlineKeyboardButton("Изменить параметр \"Команда ищет\"", callback_data="change_need#")],
                    [InlineKeyboardButton("Удалить команду", callback_data="delete#")]]
    else:
        keyboard = [[InlineKeyboardButton("Покинуть команду", callback_data="quit#")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text(text, reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return TEAM_MANAGE


async def list_requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]
    team_hash = context.user_data['team_hash']

    reader = Reader()
    not_accepted = reader.get_not_accepted_members(event_hash, team_hash)

    if not not_accepted:
            keyboard = [[InlineKeyboardButton("Назад", callback_data="back#")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            msg = await query.edit_message_text("Запросы на присоединение к команде отсутствуют. \nЕсли пользователь был "
                                                "принят в другую команду, его запрос был автоматически удален.", reply_markup=reply_markup)
            return REQUESTS_MANAGE

    keyboard = [[InlineKeyboardButton(f"@{user['alias']}", callback_data=user['member_id'])] for user in not_accepted]
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back#")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text("Выберите, на чей запрос хотите ответить.\nЕсли пользователь был "
                                                "принят в другую команду, его запрос был автоматически удален.", reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return REQUESTS_MANAGE


async def answer_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = int(query.data)

    reader = Reader()
    user_alias = reader.get_user_alias(user_id)
    context.user_data["user_id"] = user_id
    context.user_data["user_alias"] = user_alias

    keyboard = [[InlineKeyboardButton("Отклонить", callback_data="reject#"), InlineKeyboardButton("Принять", callback_data="confirm#")]]
    keyboard.append([InlineKeyboardButton("Назад", callback_data="back#")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text(f"Запрос от пользователя @{user_alias}", reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return ANSWER_REQUEST


async def confirm_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]
    team_hash = context.user_data["team_hash"]
    user_id = context.user_data["user_id"]
    user_alias = context.user_data["user_alias"]

    reader = Reader()
    event_name = reader.get_event_name(event_hash)
    team_name = reader.get_team_name(event_hash, team_hash)
    members_amount = reader.accept_member(event_hash, team_hash, user_id)

    if members_amount == 1:
        message_to_send = "Невозможно принять запрос, команда заполнена."
    elif members_amount == 2:
        message_to_send = "Пользователь был принят в другую команду."
    else:
        message_to_send = f"Пользователь @{user_alias} теперь является участником команды.\nУчастников команды {members_amount[1]}/{members_amount[0]}."
        try:
            await context.bot.send_message(chat_id=user_id, text=f"Ваш запрос на присоединение к команде \"{team_name}\" "
                                 f"в мероприятии \"{event_name}\" был принят. "
                                 f"Чтобы просмотреть информацию о команде, используйте /my_teams.")
        except Exception:
            pass

    keyboard = [[InlineKeyboardButton("ОК", callback_data="back#")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text(message_to_send, reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return REQUESTS_MANAGE


async def reject_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]
    team_hash = context.user_data["team_hash"]
    user_id = context.user_data["user_id"]
    user_alias = context.user_data["user_alias"]

    reader = Reader()
    event_name = reader.get_event_name(event_hash)
    team_name = reader.get_team_name(event_hash, team_hash)
    reader.remove_member(event_hash, team_hash, user_id)

    try:
        await context.bot.send_message(chat_id=user_id, text=f"Ваш запрос на присоединение к команде \"{team_name}\" "
                                f"в мероприятии \"{event_name}\" был отлонен. ")
    except Exception:
        pass
    keyboard = [[InlineKeyboardButton("ОК", callback_data="back#")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text(f"Запрос пользователя @{user_alias} отклонен.", reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return REQUESTS_MANAGE


async def list_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]
    team_hash = context.user_data["team_hash"]

    reader = Reader()
    members = reader.get_team_members(update.callback_query.from_user.id, event_hash, team_hash)
    keyboard = []
    if not members:
        msg_text = "Участником команды являетесь только вы."
    else:
        msg_text = "Выберите участника, которого хотите исключить."
        keyboard = [[InlineKeyboardButton(f"@{member['alias']}", callback_data=member['member_id'])] for member in members]
    keyboard.append([InlineKeyboardButton(f"Назад", callback_data='back#')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text(msg_text, reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return KICK_MEMBER


async def choose_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = int(query.data)

    reader = Reader()
    user_alias = reader.get_user_alias(user_id)
    context.user_data["user_id"] = user_id
    context.user_data["user_alias"] = user_alias

    keyboard = [[InlineKeyboardButton("Отмена", callback_data="back#"), InlineKeyboardButton("Исключить", callback_data="confirm#")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text(f"Подтвердите исключение участника @{user_alias}.", reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return CONFIRM_KICK


async def confirm_kick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]
    team_hash = context.user_data["team_hash"]
    user_id = context.user_data["user_id"]
    user_alias = context.user_data["user_alias"]

    reader = Reader()
    event_name = reader.get_event_name(event_hash)
    team_name = reader.get_team_name(event_hash, team_hash)
    reader.remove_member(event_hash, team_hash, user_id)

    try:
        await context.bot.send_message(chat_id=user_id, text=f"Вы были исключены из команды \"{team_name}\" "
                                f"в мероприятии \"{event_name}\".")
    except Exception:
        pass
    keyboard = [[InlineKeyboardButton("ОК", callback_data="back#")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text(f"Участник @{user_alias} исключен.", reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return KICK_MEMBER


async def change_team_needs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    await query.edit_message_text("Опишите, участников с какими умениями ищет ваша команда. "
                                    "Если ищете кого угодно или никого, так и напишите.", reply_markup=None)

    return CHANGE_NEEDS


async def set_new_needs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    new_needs = update.message.text
    event_hash = context.user_data["event_hash"]
    team_hash = context.user_data["team_hash"]

    reader = Reader()
    reader.change_team_needs(event_hash, team_hash, new_needs)
    team_info = reader.get_team_info(update.message.from_user.id, event_hash)

    if not team_info:
            await update.message.reply_text("Вы больше не участвуете в этом мероприятии.", reply_markup=None)
            return ConversationHandler.END
    
    context.user_data['team_hash'] = team_info['team_hash']
    
    team_info['event_hash'] = reader.get_event_name(event_hash)
    team_info['theme_hash'] = reader.get_theme_name(event_hash, team_info['theme_hash'])

    max_members = reader.get_max_members(event_hash)
    cur_members = reader.get_current_members(event_hash, team_info['team_hash'])
    team_info['members'] = f"{cur_members}/{max_members}"
    if team_info['team_opened']:
        team_info['team_opened'] = "открыта для запросов"
        flip_team_state = "Закрыть команду"
    else:
        team_info['team_opened'] = "закрыта для запросов"
        flip_team_state = "Открыть команду"
    
    info_headers = ["Мероприятие: ", "Тема: ", "Команда: ", "", "Лидер: @", "Команда ", "Команда ищет: ", "", "Участники "]
    text = ""
    for index, key in enumerate(list(team_info.keys())):
        if key == 'leader_id':
            continue
        if key == 'team_hash':
            continue
        text += info_headers[index] + str(team_info[key]) + "\n\n"

    if team_info['leader_id'] == update.message.from_user.id:
        keyboard = [[InlineKeyboardButton("Принять/отклонить запрос в команду", callback_data="answer#")],
                    [InlineKeyboardButton(flip_team_state, callback_data="flip_state#")],
                    [InlineKeyboardButton("Исключить участника", callback_data="kick#")],
                    [InlineKeyboardButton("Изменить параметр \"Команда ищет\"", callback_data="change_need#")],
                    [InlineKeyboardButton("Удалить команду", callback_data="delete#")]]
    else:
        keyboard = [[InlineKeyboardButton("Покинуть команду", callback_data="quit#")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text(text, reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return TEAM_MANAGE


async def delete_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]
    team_hash = context.user_data["team_hash"]

    reader = Reader()
    team_name = reader.get_team_name(event_hash, team_hash)

    keyboard = [[InlineKeyboardButton("Отмена", callback_data="back#"), InlineKeyboardButton("Удалить", callback_data="confirm#")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text(f"Вы уверены, что хотите удалить команду \"{team_name}\"?", reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return DELETE_TEAM


async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]
    team_hash = context.user_data["team_hash"]

    reader = Reader()
    event_name = reader.get_event_name(event_hash)
    team_name = reader.get_team_name(event_hash, team_hash)
    members_deleted = reader.delete_team(event_hash, team_hash, update.callback_query.from_user.id)

    await query.edit_message_text(f"Команда \"{team_name}\" удалена. Вы больше не участвуете в мероприятии \"{event_name}\"", reply_markup=None)

    for member_id in members_deleted:
        try:
            await context.bot.send_message(chat_id=member_id, text=f"Команда \"{team_name}\" была удалена. "
                                 f"Вы больше не участвуете в мероприятии \"{event_name}\".")
        except Exception:
            pass

    return ConversationHandler.END


async def quit_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]
    team_hash = context.user_data["team_hash"]

    reader = Reader()
    team_name = reader.get_team_name(event_hash, team_hash)

    keyboard = [[InlineKeyboardButton("Отмена", callback_data="back#"), InlineKeyboardButton("Покинуть", callback_data="confirm#")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text(f"Вы уверены, что хотите покинуть команду \"{team_name}\"?", reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return QUIT_TEAM


async def confirm_quit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]
    team_hash = context.user_data["team_hash"]

    reader = Reader()
    event_name = reader.get_event_name(event_hash)
    team_name = reader.get_team_name(event_hash, team_hash)
    leader_id = reader.get_leader_id(event_hash, team_hash)
    member_alias = update.callback_query.from_user.username
    reader.remove_member(event_hash, team_hash, update.callback_query.from_user.id)

    await query.edit_message_text(f"Вы покинули команду \"{team_name}\". Вы больше не участвуете в мероприятии \"{event_name}\"", reply_markup=None)

    try:
        await context.bot.send_message(chat_id=int(leader_id), text=f"Участник @{member_alias} покинул команду \"{team_name}\" "
                                       f"мероприятия \"{event_name}\".")
    except Exception:
        pass

    return ConversationHandler.END


async def cancel_manage_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Управление командой завершено.")
    await remove_buttons(context.chat_data)

    return ConversationHandler.END


async def set_theme_options(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    theme_hash = int(query.data)
    event_hash = context.user_data["event_hash"]
    context.user_data["theme_hash"] = theme_hash

    reader = Reader()
    theme_info = reader.theme_info(event_hash, theme_hash)

    if not theme_info:
            msg = await query.edit_message_text("Мероприятие удалено.", reply_markup=None)
            return ConversationHandler.END
    
    info_headers = ["Мероприятие: ", "Тема: ", "Заказчик: ", "Максимум команд: ", "Ответственный: ", "Email ответственного: ", "Описание темы: ", 
                    "Предпосылки: ", "Проблема: ", "Ожидаемый результат: "]
    text = ""
    for index, key in enumerate(list(theme_info.keys())):
        if key == 'theme_hash':
            continue
        if (theme_info[key] == None):
            continue
        text += info_headers[index] + str(theme_info[key]) + "\n\n"

    first_row_keyboard = []
    keyboard = []
    themes_to_join = reader.get_themes_to_join(update.callback_query.from_user.id, event_hash)
    themes_to_create = reader.get_themes_to_create(update.callback_query.from_user.id, event_hash)

    if themes_to_join != 1 and themes_to_create != 1:
        for theme in themes_to_join:
            if theme['theme_hash'] == theme_hash:
                first_row_keyboard.append(InlineKeyboardButton("Присоединиться к команде", callback_data="jump_to_join#"))
                break

        for theme in themes_to_create:
            if theme['theme_hash'] == theme_hash:
                first_row_keyboard.append(InlineKeyboardButton("Создать команду", callback_data="jump_to_create#"))
                
        keyboard.append(first_row_keyboard)

    keyboard.append([InlineKeyboardButton("Назад", callback_data="return_to_themes#")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text(text, reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return ConversationHandler.END


async def cancel_themes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Просмотр тем завершен.")
    await remove_buttons(context.chat_data)

    return ConversationHandler.END


async def list_user_events(update: Update, context: CallbackContext) -> int:
    await remove_buttons(context.chat_data)
    
    try:
        user_id = update.message.from_user.id
    except AttributeError:
        user_id = update.callback_query.from_user.id
    reader = Reader()
    events = reader.get_user_events(user_id)

    if len(events) == 0:
        await update.effective_message.reply_text("Вы не являетесь организатором ни одного мероприятия.")
        return ConversationHandler.END
    
    keyboard = [[InlineKeyboardButton(event['event'][:80], callback_data=event['event_hash'])] for event in events]
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        msg = await update.callback_query.edit_message_text("Выберите мероприятие, которое хотите удалить.", reply_markup=reply_markup)
    except AttributeError:
        msg = await update.effective_message.reply_text("Выберите мероприятие, которое хотите удалить.", reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg
    
    return EVENT_NAME


async def confirm_delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = int(query.data)
    context.user_data["event_hash"] = event_hash

    reader = Reader()
    event_name = reader.get_event_name(event_hash)

    keyboard = [[InlineKeyboardButton("Отмена", callback_data="back#"), InlineKeyboardButton("Удалить", callback_data="confirm#")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await query.edit_message_text(f"Вы уверены, что хотите удалить мероприятие \"{event_name}\"?", reply_markup=reply_markup)
    context.chat_data["buttons_message"] = msg

    return DELETE_EVENT


async def delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    event_hash = context.user_data["event_hash"]

    reader = Reader()
    event_name = reader.get_event_name(event_hash)
    reader.delete_event(event_hash)

    await query.edit_message_text(f"Мероприятие \"{event_name}\" удалено.", reply_markup=None)

    return ConversationHandler.END


async def cancel_delete_event(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Удаление мероприятия отменено.")
    await remove_buttons(context.chat_data)

    return ConversationHandler.END


def save_data():
    while True:
        sleep(3600)
        reader = Reader()
        reader.save_data()


def main() -> None:
    application = Application.builder().token("7143101973:AAEqnB854KWCeQ2aVWaf4Y2qLGbt-EZTt8k").build()

    application.add_handler(CommandHandler("start", start), group=0)
    application.add_handler(CommandHandler("help", start), group=0)

    # Создание мероприятия
    create_event_handler = ConversationHandler(
        entry_points=[CommandHandler("create_event", create_event)],
        states={
            EVENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_event_name)],
            EVENT_MAX_MEMBERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_event_max_members)],
            UPLOAD_THEMES: [MessageHandler(filters.Document.ALL, get_themes_file)]
        },
        fallbacks=[CommandHandler("cancel", cancel_create_event),
                   MessageHandler(filters.COMMAND, cancel_any)],
        allow_reentry=True)
    application.add_handler(create_event_handler, group=1)

    # Создание команды
    create_team_handler = ConversationHandler(
        entry_points=[CommandHandler("create_team", list_events),
                      CallbackQueryHandler(confirm_theme_button, pattern="^jump_to_create#$")],
        states={
            EVENT_NAME: [CallbackQueryHandler(select_event_button)],
            THEME_NAME: [CallbackQueryHandler(select_event_button, pattern="^next#$"),
                         CallbackQueryHandler(select_event_button, pattern="^back#$"),
                        CallbackQueryHandler(select_theme_button)],
            CONFIRM_THEME: [CallbackQueryHandler(select_event_button, pattern="^return#$"),
                            CallbackQueryHandler(confirm_theme_button, pattern="^next#$")],
            TEAM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_team_name)],
            TEAM_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_team_description)]
        },
        fallbacks=[CommandHandler("cancel", cancel_create_team),
                   MessageHandler(filters.COMMAND, cancel_any)],
        allow_reentry=True)
    application.add_handler(create_team_handler, group=2)

    # Присоединение к команде
    join_team_handler = ConversationHandler(
        entry_points=[CommandHandler("join_team", list_events),
                      CallbackQueryHandler(confirm_theme_button, pattern="^jump_to_join#$")],
        states={
            EVENT_NAME: [CallbackQueryHandler(select_event_button)],
            THEME_NAME: [CallbackQueryHandler(select_event_button, pattern="^next#$"),
                         CallbackQueryHandler(select_event_button, pattern="^back#$"),
                        CallbackQueryHandler(select_theme_button)],
            CONFIRM_THEME: [CallbackQueryHandler(select_event_button, pattern="^return#$"),
                            CallbackQueryHandler(confirm_theme_button, pattern="^next#$")],
            TEAM_NAME: [CallbackQueryHandler(select_team_button)],
            SEND_REQUEST: [CallbackQueryHandler(confirm_theme_button, pattern="^back#$"),
                           CallbackQueryHandler(send_join_request, pattern="^join#$")]
        },
        fallbacks=[CommandHandler("cancel", cancel_join_team),
                   MessageHandler(filters.COMMAND, cancel_any)],
        allow_reentry=True)
    application.add_handler(join_team_handler, group=3)

    # Управление командой
    manage_team_handler = ConversationHandler(
        entry_points=[CommandHandler("my_teams", list_member_events)],
        states={
            EVENT_NAME: [CallbackQueryHandler(list_team_info)],
            TEAM_MANAGE: [CallbackQueryHandler(list_requests, pattern="^answer#$"),
                         CallbackQueryHandler(list_team_info, pattern="^flip_state#$"),
                         CallbackQueryHandler(list_members, pattern="^kick#$"),
                         CallbackQueryHandler(change_team_needs, pattern="^change_need#$"),
                         CallbackQueryHandler(delete_team, pattern="^delete#$"),
                         CallbackQueryHandler(quit_team, pattern="^quit#$")],
            REQUESTS_MANAGE: [CallbackQueryHandler(list_team_info, pattern="^back#$"),
                              CallbackQueryHandler(answer_request)],
            ANSWER_REQUEST: [CallbackQueryHandler(list_requests, pattern="^back#$"),
                             CallbackQueryHandler(confirm_request, pattern="^confirm#$"),
                             CallbackQueryHandler(reject_request, pattern="^reject#$")],
            KICK_MEMBER: [CallbackQueryHandler(list_team_info, pattern="^back#$"),
                          CallbackQueryHandler(choose_member)],
            CONFIRM_KICK: [CallbackQueryHandler(list_members, pattern="^back#$"),
                            CallbackQueryHandler(confirm_kick)],
            CHANGE_NEEDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_new_needs)],
            DELETE_TEAM: [CallbackQueryHandler(confirm_delete, pattern="^confirm#$"),
                          CallbackQueryHandler(list_team_info, pattern="^back#$")],
            QUIT_TEAM: [CallbackQueryHandler(confirm_quit, pattern="^confirm#$"),
                          CallbackQueryHandler(list_team_info, pattern="^back#$")]
        },
        fallbacks=[CommandHandler("cancel", cancel_manage_team),
                   MessageHandler(filters.COMMAND, cancel_any)],
        allow_reentry=True)
    application.add_handler(manage_team_handler, group=4)

    # Просмотр всех тем
    all_themes_handler = ConversationHandler(
        entry_points=[CommandHandler("themes", list_events),
                      CallbackQueryHandler(select_event_button, pattern="^return_to_themes#$")],
        states={
            EVENT_NAME: [CallbackQueryHandler(select_event_button)],
            THEME_NAME: [CallbackQueryHandler(select_event_button, pattern="^next#$"),
                         CallbackQueryHandler(select_event_button, pattern="^back#$"),
                         CallbackQueryHandler(set_theme_options)]
        },
        fallbacks=[CommandHandler("cancel", cancel_themes),
                   MessageHandler(filters.COMMAND, cancel_any)],
        allow_reentry=True)
    application.add_handler(all_themes_handler, group=5)

    # Удаление мероприятия
    delete_event_handler = ConversationHandler(
        entry_points=[CommandHandler("delete_event", list_user_events)],
        states={
            EVENT_NAME: [CallbackQueryHandler(confirm_delete_event)],
            DELETE_EVENT: [CallbackQueryHandler(delete_event, pattern="^confirm#$"),
                         CallbackQueryHandler(list_user_events, pattern="^back#$")]
        },
        fallbacks=[CommandHandler("cancel", cancel_delete_event),
                   MessageHandler(filters.COMMAND, cancel_any)],
        allow_reentry=True)
    application.add_handler(delete_event_handler, group=6)

    save_timer = Thread(target=save_data)
    save_timer.daemon = True
    save_timer.start()

    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        reader = Reader()
        reader.save_data()
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
