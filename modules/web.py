# -*- coding: utf-8 -*-
import asyncio
import datetime
import os
import random
import string
from functools import partial, wraps
from typing import Any, Callable, Optional

import sanic
from jinja2 import Environment, FileSystemLoader
from sanic.request import Request
from sanic.response import HTTPResponse, html

from .localize import LocalizedText


bp = sanic.Blueprint(__name__)

@bp.route("/",methods=["GET"])
async def main(self, request: Request) -> HTTPResponse:
    return await request.app.render_template("index.html",{"self": request.app})


class LoginManager:
    def __init__(self, bot: 'Bot') -> None:
        self.id_len = 64
        self.expires_in = datetime.timedelta(minutes=10)
        self.expires = {}
        self.cookie_key = "X-SessionId"
        self.unauthorized_handler_ = sanic.response.html("Unauthorized")

    def generate_id(self, request: Request) -> str:
        id_ = "".join(random.choices(string.ascii_letters + string.digits, k=self.i__len))
        while id_ in self.expires.keys():
            id_ = "".join(random.choices(string.ascii_letters + string.digits, k=self.id_len))
        return id_

    def authenticated(self, request: Request) -> bool:
        if not self.bot.is_error() and self.bot.config["web"]["login_required"]:
            id_ = request.cookies.get(self.cookie_key)
            if not id_:
                return False
            elif id_ in self.expires.keys():
                return True
            else:
                return False
        else:
            return True

    def login_user(self, request: Request, response: HTTPResponse) -> None:
        id_ = self.generate_id(request)
        response.cookies[self.cookie_key] = id_
        self.expires[id_] = datetime.datetime.utcnow() + self.expires_in

    def logout_user(self, request: Request, response: HTTPResponse) -> None:
        id_ = request.cookies.get(self.cookie_key)
        if id_ is not None:
            del response.cookies[self.cookie_key]
            del self.expires[id_]
            
    def login_required(self, func: Callable) -> Callable:
        @wraps(func)
        def deco(request: Request, *args: Any, **kwargs: Any):
            if self.authenticated(request):
                return func(request, *args, **kwargs)
            elif isinstance(self.unauthorized_handler_, HTTPResponse):
                return self.unauthorized_handler_
            elif callable(self.unauthorized_handler_):
                return self.unauthorized_handler_(request, *args, **kwargs)
        return deco

    def unauthorized_handler(self, func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func) is False:
            raise ValueError("Function must be a coroutine")
        self.unauthorized_handler_ = func
        @wraps(func)
        def deco(*args: Any, **kwargs: Any):
            return func(*args, **kwargs)
        return deco


class WebUser:
    def __init__(self, sessionId: str) -> None:
        self._id = sessionId

    @property
    def display_name(self) -> str:
        return "WebUser"

    @property
    def id(self) -> str:
        return self._id


class WebMessage:
    def __init__(self, content: str, sessionId: str, client: 'Client') -> None:
        self._sessionId = sessionId
        self._content = content
        self._client = client
        self._author = WebUser(self._sessionId)
        self._messages = []
        
    @property
    def author(self) -> WebUser:
        return self._author

    @property
    def content(self) -> str:
        return self._content

    @property
    def client(self) -> 'Client':
        return self._client

    @property
    def result(self) -> str:
        return self._messages

    def reply(self, content: str) -> None:
        self._messages.append(content)


class Web(sanic.Sanic):
    def __init__(self, bot: 'Bot', *args: Any, **kwargs: Any) -> None:
        self.bot = bot

        self.env = Environment(
            loader=FileSystemLoader('./templates', encoding='utf8'),
            extensions=['jinja2.ext.do']
        )
        self.route_prefix = 'route_'

        super().__init__(*args, **kwargs)
        self.secret_key = os.urandom(32)
        self.blueprint(bp)

    def l(self, key: str, *args: tuple, default: Optional[str] = '', **kwargs: dict) -> LocalizedText:
        return LocalizedText(self.bot,['web',key],default,*args,**kwargs)

    async def render_template(self, filename: str, *args: Any, **kwargs: Any) -> HTTPResponse:
        template = self.env.get_template(filename)
        return html(await template.render_async(*args,**kwargs))