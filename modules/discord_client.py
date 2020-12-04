# -*- coding: utf-8 -*-
import asyncio
import datetime
import io
import sys
from typing import TYPE_CHECKING, Any, Callable, Optional, Union, List

import discord
import fortnitepy

from .colors import green
from .commands import MyMessage
from .localize import LocalizedText

if TYPE_CHECKING:
    from .bot import Bot


class DiscordClient(discord.Client):
    def __init__(self, bot: 'Bot', config: dict, *, loop=None, **options) -> None:
        self.bot = bot
        self.config = config

        super().__init__(loop=loop, **options)

        self.booted_at = None

        self._owner = {}
        self._whitelist = {}
        self._blacklist = {}

    # Config controls
    def fix_config(self) -> None:
        self.config['discord']['status_type'] = getattr(
            discord.ActivityType,
            self.config['discord']['status_type'].lower()
        )

    @property
    def owner(self) -> list:
        return list(self._owner.values())

    def is_owner(self, user_id: str) -> bool:
        return self._owner.get(user_id) is not None

    @property
    def whitelist(self) -> list:
        return list(self._whitelist.values())

    def is_whitelist(self, user_id: str) -> bool:
        return self._whitelist.get(user_id) is not None

    @property
    def blacklist(self) -> list:
        return list(self._blacklist.values())

    def is_blacklist(self, user_id: int) -> bool:
        return self._blacklist.get(user_id) is not None

    def get_user_type(self, user_id: int) -> str:
        if self.is_owner(user_id):
            return 'owner'
        elif self.is_whitelist(user_id):
            return 'whitelist'
        elif self.is_blacklist(user_id):
            return 'blacklist'
        elif self.get_user(user_id):
            return 'bot'
        return 'user'

    def is_for(self, config_key: str, user_id: int) -> bool:
        user_type = self.get_user_type(user_id)
        config = self.config['discord'][config_key]
        if config is None:
            return False
        return user_type in config

    def is_discord_enable_for(self, user_id: int) -> bool:
        return self.is_for('command_enable_for', user_id)

    # Basic functions
    @property
    def variables(self) -> dict:
        user = getattr(self, 'user', None)
        uptime = (datetime.datetime.now() - self.booted_at) if self.booted_at is not None else None
        if uptime is not None:
            d, h, m, s = self.bot.convert_td(uptime)
        else:
            d = h = m = s = None
        return {
            'self': self,
            'client': self,
            'bot': self,
            'discord_bot': self,
            'guild_count': len(self.guilds),
            'display_name': getattr(user, 'display_name', None),
            'id': getattr(user, 'id', None),
            'uptime': uptime,
            'uptime_days': d,
            'uptime_hours': h,
            'uptime_minutes': m,
            'uptime_seconds': s,
            'owner': self.owner,
            'whitelist': self.whitelist,
            'blacklist': self.blacklist
        }

    def eval_format(self, text: str, variables: dict) -> str:
        return self.bot.eval_format(text, variables)

    def l(self, key: str, *args: tuple, default: Optional[str] = '', **kwargs: dict) -> LocalizedText:
        return LocalizedText(self.bot, ['discord_client', key], default, *args, **kwargs)

    def send(self, content: Any,
             user_name: Optional[str] = None,
             color: Optional[Callable] = None,
             add_p: Optional[Union[Callable, List[Callable]]] = None,
             add_d: Optional[Union[Callable, List[Callable]]] = None,
             file: Optional[io.IOBase] = None) -> Optional[str]:
        file = file or sys.stdout
        content = str(content)
        color = color or (lambda x: x)
        add_p = (add_p if isinstance(add_p, list) else [add_p or (lambda x: x)])
        add_d = (add_d if isinstance(add_d, list) else [add_d or (lambda x: x)])
        if file == sys.stderr:
            add_d.append(self.bot.discord_error)
        if not self.config['no_logs'] if self.config else True:
            text = content
            for func in add_p:
                text = func(text)
            print(color(text), file=file)

        if self.bot.webhook:
            content = discord.utils.escape_markdown(content)
            name = user_name or self.user.name
            text = content
            for func in add_d:
                text = func(text)
            self.bot.webhook.send(text, name)

    def now(self) -> str:
        return self.bot.now()

    def time(self, text: str) -> str:
        return f'[{self.now()}] [{self.user.name}] {text}'

    def name(self, user: Optional[discord.User] = None) -> str:
        user = user or self.user
        if self.config['loglevel'] == 'normal':
            return user.name
        else:
            return '{0.name} / {0.id}'.format(user)

    def format_exception(self, exc: Optional[Exception] = None) -> str:
        return self.bot.print_exception(exc)

    def print_exception(self, exc: Optional[Exception] = None) -> None:
        return self.bot.print_exception(exc)

    def debug_print_exception(self, exc: Optional[Exception] = None) -> None:
        return self.bot.debug_print_exception(exc)

    async def aexec(self, body: str, variables: dict) -> Optional[bool]:
        flag = False
        for line in body.split('\n'):
            match = self.bot.return_pattern.fullmatch(line)
            if match is not None:
                flag = True
                break
        try:
            await self.bot.aexec(body, variables)
            if flag:
                return False
        except Exception as e:
            self.print_exception(e)

    async def exec_event(self, event: str, variables: dict) -> None:
        if self.config['fortnite']['exec'][event]:
            return await self.aexec(
                self.config['discord']['exec'][event],
                variables
            )

    async def update_owner(self) -> None:
        self._owner = {}
        if self.config['discord']['owner'] is None:
            return
        for owner in self.config['discord']['owner']:
            user = self.get_user(owner)
            if user is None:
                try:
                    user = await self.fetch_user(owner)
                except discord.NotFound as e:
                    self.debug_print_exception(e)
            if user is None:
                self.send(
                    self.l(
                        'owner_not_found',
                        owner
                    ),
                    add_p=self.time
                )
            else:
                self._owner[user.id] = user
                self.send(
                    self.l(
                        'owner_log',
                        self.name(user)
                    ),
                    color=green,
                    add_p=self.time
                )

    async def _update_user_list(self, lists: list, keys_list: list) -> None:
        for keys, list_users in zip(keys_list, lists):
            attr = keys[-1]
            setattr(self, f'_{attr}', {})
            for list_user in list_users:
                user = self.get_user(list_user)
                if user is None:
                    try:
                        user = await self.fetch_user(list_user, cache=True)
                    except discord.NotFound as e:
                        self.debug_print_exception(e)
                if user is None:
                    self.send(
                        self.l(
                            'list_user_not_found',
                            self.l(attr),
                            list_user
                        ),
                        add_p=self.time,
                        add_d=self.discord_error,
                        file=sys.stderr
                    )
                else:
                    getattr(self, f'_{attr}')[user.id] = user
                    self.send(
                        self.l(
                            'list_user_log',
                            self.l(attr),
                            self.name(user)
                        ),
                        color=green,
                        add_p=self.time
                    )

    async def update_user_lists(self) -> None:
        keys_list = [
            ['discord', 'whitelist'],
            ['discord', 'blacklist']
        ]
        lists = [self.bot.get_dict_key(self.config, keys)
                 for keys in keys_list
                 if self.bot.get_dict_key(self.config, keys) is not None]
        await self._update_user_list(
            lists,
            keys_list
        )

    async def update_status(self) -> None:
        activity = discord.Activity(
            name=self.eval_format(self.config['discord']['stauts'], self.variables),
            type=self.config['discord']['status_type']
        )
        await self.change_presence(activity=activity)

    async def status_loop(self) -> None:
        while True:
            try:
                await self.update_status()
            except Exception as e:
                self.debug_print_exception(e)
            await asyncio.sleep(30)

    # Events
    async def on_ready(self) -> None:
        self.booted_at = datetime.datetime.now()
        self.loop.create_task(self.status_loop())

        self.send(
            self.l(
                'ready',
                self.name()
            ),
            color=green,
            add_p=self.time
        )
        ret = await self.exec_event('ready', {**locals(), **self.variables})
        if ret is False:
            return

        try:
            await self.update_owner()
        except Exception as e:
            self.send(
                (f'{self.format_exception(e)}\n{e}\n'
                 + self.l(
                     'error_while_updating_owner'
                 )),
                file=sys.stderr
            )
        try:
            await self.update_user_lists()
        except Exception as e:
            self.send(
                (f'{self.format_exception(e)}\n{e}\n'
                 + self.l(
                     'error_while_updating_list'
                 )),
                file=sys.stderr
            )

    async def on_message(self, message: discord.Message) -> None:
        if not self.is_ready():
            await self.wait_until_ready()

        if message.author.bot or not self.is_discord_enable_for(message.author.id):
            return

        if isinstance(self.bot, fortnitepy.Client):
            mapping = {
                'name': self.bot.user.display_name,
                'id': self.bot.user.id,
                'num': self.bot.num
            }
            if not any([message.channel.name == self.bot.cleanup_channel_name(c.format_map(mapping))
                        for c in self.config['discord']['channels']]):
                return
        else:
            if message.channel.name not in self.config['discord']['channels']:
                return

        self.send(
            message.content,
            user_name=self.name(message.author),
            add_p=[lambda x: f'{self.name(message.author)} | {x}', self.time]
        )

        mes = MyMessage(self.bot, message)
        await self.bot.process_command(mes)
