import asyncio
import sqlite3
import sys
# Скругляем миниатюры
import webbrowser
from threading import Thread
from typing import Union

import vk_api
from PyQt5 import QtGui
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from loguru import logger
from vk import VK
from vk.types.community import Community
from vk.types.responses.messages import GetConversationsItem
from vk.types.user import User
from vk_api.longpoll import VkLongPoll, VkEventType

# Пока ничего не придумал
TITLE = "Мессенджер"
# Клиент ВК
vk = VK("")
# Приложение iPhone
CLIENT_ID = "3140623"
CLIENT_PASSWORD = "VeWdmVclDCtn6ihuP1nt"

# Логгер
format = "<red>{time:YYYY-MM-DD HH:mm:ss:SSS}</red> | <lvl>{level}:\t{message}</lvl>"
logger.remove()
logger.add(sys.stdout, format=format, enqueue=True)


def circular_thumbnail(data: bytearray, type="jpg", size=50) -> QImage:
    """Делает миниатюры круглыми, из сырого изображения в QImage"""
    image = QImage.fromData(data, type)
    # Конвертация
    image.convertToFormat(QImage.Format_ARGB32)

    # Пустое изображение на котором будут рисовать
    result = QImage(
        size,
        size,
        QImage.Format_ARGB32
    )
    # Заполнить прозрачностью
    result.fill(Qt.transparent)

    # Холст
    painter = QPainter(result)
    # Кисть
    brush = QBrush(image)
    painter.setBrush(brush)
    # Без обводки
    painter.setPen(Qt.NoPen)
    # Сглаживание
    painter.setRenderHint(QPainter.HighQualityAntialiasing, True)
    # Рисовка самого круга
    painter.drawEllipse(
        0,
        0,
        size,
        size
    )
    # Конец
    painter.end()

    return result


async def auth(
        login: str,
        password: str,
        client_id=CLIENT_ID,
        client_password=CLIENT_PASSWORD):
    """Функция для авторизации и получения токена"""
    global db
    data = {
        "client_id": client_id,
        "client_secret": client_password,
        "grant_type": "password",
        "username": login,
        "password": password,
        "scope": "all",
        "v": 5.107
    }
    # Сам запрос
    r = await vk.client.post(
        "https://oauth.vk.com/token",
        data=data
    )
    r = await r.json()
    # Добавление в БД
    try:
        db.add_account(
            access_token=r["access_token"],
            user_id=r["user_id"]
        )
    except:
        logger.error("Ошибка БД, скорее всего пользователь уже есть в БД")
    return r["access_token"]


class Cache:
    """Кэш для ускорения"""
    # Кэш для миниатюр
    thumbnails = dict()
    # Кэш для сообщений
    messages = dict()


class Database:
    """Класс для работы с БД"""

    def __init__(self):
        """Инициализация подключения к БД"""
        self.connection = sqlite3.connect("vk.db", check_same_thread=False)

    def add_account(self, access_token: str, user_id: int):
        """Добавить аккаунт"""
        cursor = self.connection.cursor()
        cursor.execute(f"INSERT INTO accounts(token, vk_id) VALUES(?, ?)", (access_token, user_id))
        self.connection.commit()
        cursor.close()

    def get_accounts(self):
        """Получить все аккаунты из БД"""
        cursor = self.connection.cursor()
        result = cursor.execute("SELECT * FROM accounts").fetchall()
        cursor.close()
        return result

    def get_account(self):
        """Получить первый аккаунт из БД"""
        return self.get_accounts()[0]


class QLabelClickable(QLabel):
    """Расширенный QLabel с возможностью обрабатывать нажатия"""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        QLabel.__init__(self, parent)

    def mousePressEvent(self, ev):
        self.clicked.emit()


class AuthForm(QWidget):
    """Меню авторизации"""

    def __init__(self):
        # Инициализация родителя
        super().__init__()

        # Инициализация графики
        self.initUi()

    def initUi(self):
        """Инициализация графики"""
        # Установка размеров окна
        self.setFixedSize(360, 500)
        # Установка заголовка окна
        self.setWindowTitle(TITLE)
        # Установка таблицы стилей
        self.setStyleSheet("""
            QWidget {
                background: white;
                font-family: Roboto;
            }
            
            QPushButton[SubmitButton=true] {
                min-width: 100px;
                min-height: 30px;
                
                background-color: white;
                
                border: 2px;
                border-color: #4593ee;
                border-style: solid;
                border-radius: 20px;
                
                font-size: 12pt;
            }
            QPushButton[SubmitButton=true]:hover {
                color: white;
                background-color: #4593ee;
            }
            
            QLineEdit[AuthForm=true] {
                color: #555;
                
                border: none;
                border-bottom: 2px;
                border-style: solid;
                border-color: #dbdbdb;
            
                font-family: Roboto;
                font-size: 18px;
            }
            
            QLineEdit[AuthForm=true]:focus {
                border-color: #4593ee;
            }
            """)
        # Инициализация кнопки авторизации
        self.initLoginButton()
        # Инициализация полей данных авторизации
        self.initForms()
        # Инициализация ссылок снизу
        self.initFooterLabels()
        # Инициализация логотипа
        self.initLogo()

    def initLoginButton(self):
        self.loginButton = QPushButton(self)
        self.loginButton.setGeometry(200, 360, 120, 40)
        self.loginButton.setText("Войти")
        self.loginButton.setProperty("SubmitButton", True)
        self.loginButton.clicked.connect(self.tryAuthEvent)

    def initForms(self):
        """Инициализация полей данных авторизации"""
        self.initLoginForm()
        self.initPasswordForm()
        # Инициализация иконок
        self.initIcons()

    def initLoginForm(self):
        """Инициализация поля логина"""
        self.loginForm = QLineEdit(self)
        self.loginForm.setGeometry(40, 220, 280, 40)
        self.loginForm.setPlaceholderText("Номер телефона, почта")
        self.loginForm.setProperty("AuthForm", True)

    def initPasswordForm(self):
        """Инициализация поля пароля"""
        self.passwordForm = QLineEdit(self)
        self.passwordForm.setGeometry(40, 290, 280, 40)
        self.passwordForm.setPlaceholderText("Пароль")
        self.passwordForm.setEchoMode(QLineEdit.Password)
        self.passwordForm.setProperty("AuthForm", True)

    def initFooterLabels(self):
        """Инициализация ссылок снизу"""
        self.initRegistrationLabel()
        self.initForgotPasswordLabel()

    def initRegistrationLabel(self):
        """Инициализация ссылки на регистрацию"""
        self.registrationLabel = QLabelClickable(self)
        self.registrationLabel.setGeometry(80, 460, 90, 30)
        self.registrationLabel.setText("Регистрация")
        self.registrationLabel.setCursor(Qt.PointingHandCursor)
        self.registrationLabel.clicked.connect(self.registerEvent)

    def initForgotPasswordLabel(self):
        """Инициализация ссылки на восстановление пароля"""
        self.forgotPasswordLabel = QLabelClickable(self)
        self.forgotPasswordLabel.setGeometry(180, 460, 90, 30)
        self.forgotPasswordLabel.setText("Забыли пароль?")
        self.forgotPasswordLabel.setCursor(Qt.PointingHandCursor)
        self.forgotPasswordLabel.clicked.connect(self.forgotPasswordEvent)

    def initLogo(self):
        """Инициализация логотипа"""
        self.vkLogo = QLabel(self)
        self.vkLogo.setGeometry(30, 30, 220, 160)
        self.vkLogo.setAutoFillBackground(False)
        self.vkLogo.setPixmap(QtGui.QPixmap(":/logos/vk"))

    def initIcons(self):
        """Инициализация иконок"""
        self.initemailIcon()
        self.initpasswordIcon()

    def initemailIcon(self):
        """Инициализация иконки почты"""
        self.emailIcon = QLabel(self)
        self.emailIcon.setGeometry(10, 230, 20, 20)
        self.emailIcon.setScaledContents(True)
        self.emailIcon.setPixmap(QtGui.QPixmap(":/icons/email"))

    def initpasswordIcon(self):
        """Инициализация иконки пароля"""
        self.passwordIcon = QLabel(self)
        self.passwordIcon.setGeometry(10, 300, 20, 20)
        self.passwordIcon.setScaledContents(True)
        self.passwordIcon.setPixmap(QtGui.QPixmap(":/icons/password"))

    def tryAuthEvent(self):
        global api
        coro = auth(self.loginForm.text(), self.passwordForm.text())
        # Корутины надо запускать в отдельном потоке
        token = asyncio.run_coroutine_threadsafe(coro, loop).result()
        vk.access_token = token
        api = vk.get_api()
        Thread(target=longpoll_thread, args=(token,)).start()
        messages = Messages(self)
        messages.show()
        self.close()

    def registerEvent(self):
        webbrowser.open("https://vk.com/join")

    def forgotPasswordEvent(self):
        login = self.loginForm.text()
        link = "https://vk.com/restore"
        if login:
            link += f"?login={login}"
        webbrowser.open(link)


class Messages(QWidget):
    """Основное окно сообщений"""

    def __init__(self):
        # Инициализация родителя
        super().__init__()

        # Инициализация графики
        self.initUi()

    def initUi(self):
        """Инициализация графики"""
        # Установка размеров окна
        self.resize(800, 500)
        # Установка заголовка окна
        self.setWindowTitle(TITLE)
        self.layout = QHBoxLayout()
        self.setLayout(self.layout)

        self.setStyleSheet("""
            QWidget {
                background: white;
                font-family: Roboto;
                font-size: 12pt;
            }
        """)

        # Инициализация скролла
        self.initScroll()

        # Инициализация и загрузка диалогов
        self.initConversations()

    def initScroll(self):
        """Инициализация скролла"""
        # Макет скролла
        self.scrollLayout = QVBoxLayout()

        # Виджет скролла
        self.scrollWidget = QWidget()
        self.scrollWidget.setLayout(self.scrollLayout)

        # Область прокрутки
        self.scrollArea = QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setWidget(self.scrollWidget)
        # self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scrollArea.ensureVisible(0, 0, 0, 0)

        # Добавление в главный макет
        self.layout.addWidget(self.scrollArea)

    def initConversations(self):
        """Инициализация бесед"""
        # Список бесед
        coro = api.messages.get_conversations(
            count=20,
            extended=True
        )
        # Корутины надо запускать в отдельном потоке
        conversations = asyncio.run_coroutine_threadsafe(coro, loop).result().response
        # По хорошему бы это всё в таски, но у меня не вышло их запустить(
        for conversation in conversations.items:
            box = ConversationBox(conversation, conversations.profiles, conversations.groups)
            # Добавляем в макет скролла
            self.scrollLayout.addWidget(box)


class ConversationBox(QGroupBox):
    def __init__(self, obj: GetConversationsItem, profiles: list, groups: list, *args, **kwargs):
        # Инициализация родителя
        super().__init__(*args, **kwargs)
        # Для удобства, чтобы не городить длинные строки
        self.conversation = obj.conversation
        self.last_message = obj.last_message
        # Тип беседы: пользователь, чат, группа
        self.type = self.conversation.peer.type
        # Айди беседы
        self.peer_id = self.conversation.peer.id
        # Объект пользователя или группы
        self.obj: Union[User, Community] = None
        # Заголовок
        self.title = ""
        # Миниатюра
        self.thumbnail = None
        if self.type == "group":
            for group in groups:
                if group.id == abs(self.peer_id):
                    self.obj = group
                    break
            # Заголовок
            try:
                self.title = self.obj.name
            except:
                logger.warning("Объект группы не был передан в groups")
            # Миниатюра
            coro = vk.client.get(self.obj.photo_50)
            r = asyncio.run_coroutine_threadsafe(coro, loop).result()
            self.thumbnail = asyncio.run_coroutine_threadsafe(r.read(), loop).result()
            Cache.thumbnails[self.peer_id] = self.thumbnail
        elif self.type == "user":
            for user in profiles:
                if user.id == self.peer_id:
                    self.obj = user
                    break
            # Заголовок
            try:
                self.title = f"{self.obj.first_name} {self.obj.last_name}"
            except:
                logger.warning("Объект пользователя не был передан в profiles")
            # Миниатюра
            coro = vk.client.get(self.obj.photo_50)
            r = asyncio.run_coroutine_threadsafe(coro, loop).result()
            self.thumbnail = asyncio.run_coroutine_threadsafe(r.read(), loop).result()
            Cache.thumbnails[self.peer_id] = self.thumbnail
        elif self.type == "chat":
            # Заголовок
            try:
                self.title = self.conversation.chat_settings.title
            except:
                logger.warning("Название не было передано")
            # Миниатюра
            try:
                # В библиотеке немножко сломаны схемы, я уже отправил PR. Пока что увы так
                coro = vk.api_request(
                    "messages.getConversationsById",
                    params={
                        "peer_ids": self.peer_id
                    }
                )
                # Корутины надо запускать в отдельном потоке
                pics = asyncio.run_coroutine_threadsafe(coro, loop).result()["items"][0]["chat_settings"]["photo"]
                coro = vk.client.get(pics["photo_50"])
                r = asyncio.run_coroutine_threadsafe(coro, loop).result()
                self.thumbnail = asyncio.run_coroutine_threadsafe(r.read(), loop).result()
                Cache.thumbnails[self.peer_id] = self.thumbnail
            except:
                pass
        else:
            logger.error("Неизвестный тип беседы")

        # Инициализация графики
        self.initUi()

    def initUi(self):
        """Инициализация графики"""
        self.setStyleSheet("""
            QGroupBox {
                background-color: white;
                
                border: 0px;
                
                color: #555;
                font-family: Roboto;
                font-size: 18px;
            }
            
            QGroupBox:hover {
                background-color: #f5f7fa;
            }
            
            QGroupBox:title {
                subcontrol-origin: margin;
                left: 7px;
                padding: 0px 5px 0px 5px;
            }
        """)
        # Размеры
        self.setMinimumHeight(100)
        self.setMaximumHeight(100)
        # Курсор при наведении
        self.setCursor(Qt.PointingHandCursor)
        # Заголовок беседы
        self.setTitle(self.title)
        # Обработка нажатия
        self.clicked.connect(self.openDialogEvent)
        # Инициализация миниатюры
        self.initThumbnail()
        # Инициализация последнего сообщения
        self.initLastMessage()

    def initThumbnail(self):
        """Инициализация миниатюры"""
        # Основной текст в котором будет миниатюра
        self.thumbnailLabel = QLabel(self)
        # Установка QPixmap и закругление фото
        self.thumbnailPixmap = QPixmap(circular_thumbnail(self.thumbnail))
        self.thumbnailLabel.setPixmap(self.thumbnailPixmap)
        # Положение
        self.thumbnailLabel.move(10, 32)

    def initLastMessage(self):
        """Инициализация последнего сообщения"""
        self.lastMessageText = QLabel(self)
        self.lastMessageText.setText(self.last_message.text)
        self.lastMessageText.move(90, 50)

    def openDialogEvent(self):
        pass


def event_loop():
    loop.run_forever()


def longpoll_thread(token: str):
    global events
    vk_session = vk_api.VkApi(token=token)
    longpoll = VkLongPoll(vk_session)
    for event in longpoll.listen():
        if event.type == VkEventType.MESSAGE_NEW:
            logger.info(f"Новое сообщение\nОт: {event.user_id}\nВ: {event.peer_id}\nТекст: {event.text}\n")


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    Thread(target=event_loop).start()

    events = list()
    # База данных
    db = Database()
    accounts = db.get_accounts()
    api = vk.get_api()
    if len(accounts) >= 1:
        access_token = accounts[0][1]
        vk.access_token = access_token
        coroutine = vk.api_request("users.get", params={})
        r = asyncio.run_coroutine_threadsafe(coroutine, loop).result()[0]
        Thread(target=longpoll_thread, args=(access_token,)).start()
        app = QApplication([])
        mess = Messages()
        mess.show()
        app.exec()
    else:
        app = QApplication([])
        form = AuthForm()
        form.show()
        app.exec()
