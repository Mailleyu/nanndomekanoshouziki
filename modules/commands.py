# -*- coding: utf-8 -*-
import asyncio
import datetime
import json
import os
import random
import sys
from functools import partial
from typing import TYPE_CHECKING, Awaitable, Callable, Optional, Union

import discord
import fortnitepy

from .colors import yellow

if TYPE_CHECKING:
    from .bot import Bot
    from .client import Client

Clients = Union[
    'Bot',
    'Client'
]
Messages = Union[
    fortnitepy.FriendMessage,
    fortnitepy.PartyMessage,
    discord.Message
]
Users = Union[
    fortnitepy.User,
    fortnitepy.Friend,
    fortnitepy.PartyMember,
    discord.User,
    discord.Member
]


class PartyPrivacy(fortnitepy.Enum):
    PUBLIC = {
        'partyType': 'Public',
        'inviteRestriction': 'AnyMember',
        'onlyLeaderFriendsCanJoin': False,
        'presencePermission': 'Anyone',
        'invitePermission': 'Anyone',
        'acceptingMembers': True,
    }
    FRIENDS_ALLOW_FRIENDS_OF_FRIENDS = {
        'partyType': 'FriendsOnly',
        'inviteRestriction': 'AnyMember',
        'onlyLeaderFriendsCanJoin': False,
        'presencePermission': 'Anyone',
        'invitePermission': 'Anyone',
        'acceptingMembers': True,
    }
    FRIENDS = {
        'partyType': 'FriendsOnly',
        'inviteRestriction': 'LeaderOnly',
        'onlyLeaderFriendsCanJoin': True,
        'presencePermission': 'Leader',
        'invitePermission': 'Leader',
        'acceptingMembers': False,
    }
    PRIVATE_ALLOW_FRIENDS_OF_FRIENDS = {
        'partyType': 'Private',
        'inviteRestriction': 'AnyMember',
        'onlyLeaderFriendsCanJoin': False,
        'presencePermission': 'Noone',
        'invitePermission': 'Anyone',
        'acceptingMembers': False,
    }
    PRIVATE = {
        'partyType': 'Private',
        'inviteRestriction': 'LeaderOnly',
        'onlyLeaderFriendsCanJoin': True,
        'presencePermission': 'Noone',
        'invitePermission': 'Leader',
        'acceptingMembers': False,
    }


class FindUserMatchMethod(fortnitepy.Enum):
    FULL = 'full'
    CONTAINS = 'contains'
    STARTS = 'starts'
    ENDS = 'ends'


class FindUserMode(fortnitepy.Enum):
    DISPLAY_NAME = 'display_name'
    ID = 'id'
    NAME_ID = 'name_id'


class DummyMessage:
    def __init__(self, client: Clients, message: Messages, *,
                 content: Optional[str] = None,
                 author: Optional[Users] = None) -> None:
        self.client = client

        self.message = (
            message
            if not isinstance(message, self.__class__) else
            message.message
        )
        self.content = content or message.content

        self.author = author or message.author
        self.created_at = message.created_at

        self.result = ''

    def reply(self, content: str) -> None:
        self.result += f'\n{content}'


class MyMessage:
    def __init__(self, client: Clients, message: Messages, *,
                 content: Optional[str] = None,
                 author: Optional[Users] = None) -> None:
        self.client = client

        self.message = (
            message
            if not isinstance(message, self.__class__) else
            message.message
        )
        self.content = content or message.content

        self.args = self.content.split(' ')
        self.author = author or message.author
        self.created_at = message.created_at
        self.prev = None

    def is_discord_message(self) -> bool:
        return isinstance(self.message, discord.Message)

    def is_friend_message(self) -> bool:
        return isinstance(self.message, fortnitepy.FriendMessage)

    def is_party_message(self) -> bool:
        return isinstance(self.message, fortnitepy.PartyMessage)

    async def reply(self, content: str) -> None:
        content = str(content)
        if isinstance(self.message, fortnitepy.message.MessageBase):
            await self.message.reply(content)
        elif isinstance(self.message, discord.Message):
            lines = content.split('\n')
            texts = []
            num = 0
            for line in lines:
                if self.client.bot.get_list_index(texts, num) is None:
                    texts.append('')
                if len(texts[num] + line) < 2000:
                    texts[num] += line
                else:
                    if texts[num] == '':
                        s = [line[i:i + 2000] for i in range(0, len(line), 2000)]
                        for l in s:
                            texts[num] = l
                            num += 1
                    else:
                        num += 1
                        texts[num] = line
            for text in texts:
                await self.message.channel.send(text)
        elif isinstance(self.message, DummyMessage):
            self.message.reply(content)

        # TODO: Add WebMessage


class Command:
    def __init__(self, coro: Awaitable, **kwargs) -> None:
        if not asyncio.iscoroutinefunction(coro):
            raise TypeError('Command callback must be a coroutine')

        async def callback(*args, **kwargs):
            await coro(self, *args, **kwargs)

        self.callback = callback

        self.name = kwargs.get('name') or coro.__name__
        self.usage = kwargs.get('usage')


def command(name: Optional[str] = None,
            cls: Optional[Command] = None,
            **attrs: dict) -> callable:
    cls = cls or Command

    def deco(func):
        if isinstance(func, Command):
            raise TypeError('Callback is already a command.')
        return cls(func, name=name, **attrs)

    return deco


async def add_to_list(attr: str, message: MyMessage, user: fortnitepy.User):
    client = message.client

    if user.id in getattr(client, f'_{attr}'):
        await message.reply(
            client.l(
                'already_in_list',
                client.l(attr),
                client.name(user)
            )
        )
        return
    getattr(client, f'_{attr}')[user.id] = user
    config = client.bot.load_json('config')
    try:
        config['clients'][client.num]
    except (KeyError, IndexError) as e:
        client.debug_print_exception(e)
        await message.reply(
            client.l('failed_to_load_config_index')
        )
        return
    if config['clients'][client.num]['fortnite'][attr] is None:
        config['clients'][client.num]['fortnite'][attr] = []
    config['clients'][client.num]['fortnite'][attr].append(client.get_user_str(user))
    client.bot.save_json('config', config)
    await message.reply(
        client.l(
            'add_to_list',
            client.l(attr),
            client.name(user)
        )
    )


async def remove_from_list(attr: str, message: MyMessage, user: fortnitepy.User):
    client = message.client

    if user.id not in getattr(client, f'_{attr}'):
        await message.reply(
            client.l(
                'not_in_list',
                client.l(attr),
                client.name(user)
            )
        )
        return
    getattr(client, f'_{attr}').pop[user.id]
    config = client.bot.load_json('config')
    try:
        config['clients'][client.num]
    except (KeyError, IndexError) as e:
        client.debug_print_exception(e)
        await message.reply(
            client.l('failed_to_load_config_index')
        )
        return
    if config['clients'][client.num]['fortnite'][attr] is None:
        config['clients'][client.num]['fortnite'][attr] = []
    config['clients'][client.num]['fortnite'][attr].append(client.get_user_str(user))
    client.bot.save_json('config', config)
    await message.reply(
        client.l(
            'remove_from_list',
            client.l(attr),
            client.name(user)
        )
    )


async def list_operation(func: Callable, attr: str, command: Command,
                         client: 'Client', message: MyMessage) -> None:
    if len(message.args) < 2:
        await client.show_help(command, message)
        return

    users = client.find_users(
        ' '.join(message.args[1:]),
        mode=FindUserMode.NAME_ID,
        method=FindUserMatchMethod.CONTAINS,
        me=message.author
    )

    if len(users) > client.config['search_max']:
        await message.reply(
            client.l('too_many', client.l('user'), len(users))
        )
        return

    if len(users) == 0:
        await message.reply(
            client.l(
                'not_found',
                client.l('user'),
                ' '.join(message.args[1:])
            )
        )
    elif len(users) == 1:
        await func(attr, message, users[0])
    else:
        client.select[message.author.id] = {
            'exec': f'await {func.__name__}(attr, message, user)',
            'globals': {**globals(), **locals()},
            'variables': [
                {'user': user}
                for user in users
            ]
        }
        await message.reply(
            ('\n'.join([f'{num}: {client.name(user)}'
                        for num, user in enumerate(users, 1)])
                + '\n' + client.l('enter_number_to_select', client.l(attr)))
        )


async def all_cosmetics(item: str, client: 'Client', message: MyMessage) -> None:
    attr = f'is_{client.bot.convert_backend_to_key(item)}_lock_for'
    if getattr(client, attr)(message.author.id):
        await message.reply(
            client.l('cosmetic_locked')
        )
        return

    async def all_cosmetics():
        cosmetics = [
            i for i in client.bot.main_items.values()
            if i['type']['backendValue'] == item
        ]
        for cosmetic in cosmetics:
            if getattr(client, attr)(message.author.id):
                await message.reply(
                    client.l('cosmetic_locked')
                )
                return

            await client.party.me.change_asset(
                cosmetic['type']['backendValue'],
                cosmetic['id'],
                keep=False
            )
            await message.reply(
                f'{cosmetic["type"]["displayValue"]}: {client.name_cosmetic(cosmetic)}'
            )
            await asyncio.sleep(5)
    await message.reply(
        client.l(
            'has_end',
            client.l(client.bot.convert_backend_to_key(item))
        )
    )

    task = client.loop.create_task(all_cosmetics())
    client.stoppable_tasks.append(task)


async def cosmetic_search(item: Optional[str], mode: str, command: Command,
                          client: 'Client', message: MyMessage) -> None:
    if len(message.args) < 2:
        await client.show_help(command, message)
        return

    async def set_cosmetic(cosmetic):
        item = cosmetic["type"]["backendValue"]
        attr = f'is_{client.bot.convert_backend_to_key(item)}_lock_for'
        if getattr(client, attr)(message.author.id):
            await message.reply(
                client.l('cosmetic_locked')
            )
            return
        await client.party.me.change_asset(item, cosmetic['id'])
        await message.reply(
            client.l(
                'set_to',
                cosmetic['type']['displayValue'],
                client.name_cosmetic(cosmetic)
            )
        )

    cosmetics = client.searcher.search_item(mode, ' '.join(message.args[1:]), item)

    if len(cosmetics) > client.config['search_max']:
        await message.reply(
            client.l('too_many', client.l('item'), len(cosmetics))
        )
        return

    if len(cosmetics) == 0:
        await message.reply(
            client.l(
                'not_found',
                client.l('item'),
                ' '.join(message.args[1:])
            )
        )
        return

    if len(cosmetics) == 1:
        await set_cosmetic(cosmetics[0])
    else:
        client.select[message.author.id] = {
            'exec': 'await set_cosmetic(cosmetic)',
            'globals': {**globals(), **locals()},
            'variables': [
                {'cosmetic': cosmetic}
                for cosmetic in cosmetics
            ]
        }
        await message.reply(
            ('\n'.join([f'{num}: {client.name_cosmetic(cosmetic)}'
                        for num, cosmetic in enumerate(cosmetics, 1)])
                + '\n' + client.l('enter_number_to_select', client.l('item')))
        )


async def playlist_search(mode: str, command: Command,
                          client: 'Client', message: MyMessage) -> None:
    if len(message.args) < 2:
        await client.show_help(command, message)
        return

    async def set_playlist(message, playlist):
        if not client.party.leader:
            await message.reply(
                client.l('not_a_party_leader')
            )
            return
        try:
            await client.party.set_playlist(playlist['id'])
        except fortnitepy.Forbidden:
            await message.reply(
                client.l('not_a_party_leader')
            )
            return
        await message.reply(
            client.l(
                'set_to',
                client.bot.l('playlist'),
                client.name_cosmetic(playlist)
            )
        )

    playlists = client.searcher.search_playlist(
        mode,
        ' '.join(message.args[1:])
    )

    if len(playlists) > client.config['search_max']:
        await message.reply(
            client.l('too_many', client.l('playlist'), len(playlists))
        )
        return

    if len(playlists) == 0:
        await message.reply(
            client.l(
                'not_found',
                client.l('playlist'),
                ' '.join(message.args[1:])
            )
        )
    elif len(playlists) == 1:
        await set_playlist(message, playlists[0])
    else:
        client.select[message.author.id] = {
            'exec': 'await set_playlist(message, playlist)',
            'globals': {**globals(), **locals()},
            'variables': [
                {'playlist': playlist}
                for playlist in playlists
            ]
        }
        await message.reply(
            ('\n'.join([f'{num}: {client.name_cosmetic(playlist)}'
                        for num, playlist in enumerate(playlists, 1)])
                + '\n' + client.l('enter_number_to_select', client.bot.l('playlist')))
        )


# TODO: :thinking:
"""async def set_config_key(keys: List[str], lang_key: str, command: Command,
                         client: 'Client', message: MyMessage,
                         allow_username: Optional[bool] = False) -> None:
    if len(message.args) < 2:
        await client.show_help(command, message)
        return

    for user_type in [i['real_value'] for i in client.bot.multiple_select_user_type]:
        if message.args[1] in client.commands[user_type]:
            client.bot.set_dict_key(client.config, keys, True)
            await message.reply(
                client.l(
                    'set_to',
                    client.l(lang_key),
                    client.l('on')
                )
            )

    if message.args[1] in client.commands['true']:
        client.bot.set_dict_key(client.config, keys, True)
        await message.reply(
            client.l(
                'set_to',
                client.l(lang_key),
                client.l('on')
            )
        )
    elif message.args[1] in client.commands['false']:
        client.bot.set_dict_key(client.config, keys, False)
        await message.reply(
            client.l(
                'set_to',
                client.l(lang_key),
                client.l('off')
            )
        )
    elif allow_username:
        async def set_config_key(user):
            client.bot.set_dict_key(client.config, keys, client.get_user_str(user))
            await message.reply(
                client.l(
                    'set_to',
                    client.l(lang_key),
                    client.name(user)
                )
            )

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            me=message.author
        )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await set_config_key(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await set_config_key(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )
    else:
        await client.show_help(command, message)"""


class DefaultCommands:
    @command(
        name='exec',
        usage='{name} [code]'
    )
    async def exec(command: Command, client: 'Client', message: MyMessage) -> None:
        var = globals()
        var.update(locals())
        var.update(client.variables)
        result, out, err = await client.bot.aexec(' '.join(message.args[1:]), var)
        if out:
            client.send(out)
        if err:
            client.send(
                err,
                file=sys.stderr
            )
        client.send(
            str(result),
            add_p=client.time
        )
        await message.reply(str(result))

    @command(
        name='clear',
        usage='{name}'
    )
    async def clear(command: Command, client: 'Client', message: MyMessage) -> None:
        if sys.platform == 'win32':
            os.system('cls')
        else:
            os.system('clear')
        await message.reply(
            client.l('console_clear')
        )

    @command(
        name='help',
        usage='{name} [{client.l("command")}]'
    )
    async def help(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        cmd = client.commands.get(message.args[1])
        if cmd is None:
            for identifier, words in client.commands['commands'].items():
                if message.args[1] in words:
                    cmd = client.all_commands[identifier]
                    break
            else:
                await message.reply(
                    client.l('please_enter_valid_number')
                )
                return

        await client.show_help(cmd, message)

    @command(
        name='ping',
        usage='{name}'
    )
    async def ping(command: Command, client: 'Client', message: MyMessage) -> None:
        latency = abs((datetime.datetime.utcnow() - message.created_at).total_seconds())
        await message.reply(
            client.l('ping', int(latency * 1000))
        )

    @command(
        name='prev',
        usage='{name}'
    )
    async def prev(command: Command, client: 'Client', message: MyMessage) -> None:
        if message.prev is not None:
            await client.process_command(message.prev)

    @command(
        name='send_all',
        usage='{name} [{client.l("message")}]'
    )
    async def send_all(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        tasks = []
        for c in client.bot.clients:
            mes = DummyMessage(c, message, content=' '.join(message.args[1:]))
            c.send(
                mes.content,
                user_name=c.name(mes.author),
                add_p=[lambda x: f'{c.name(mes.author)} | {x}', c.time]
            )
            task = client.loop.create_task(c.process_command(MyMessage(c, mes)))
            tasks.append((c, mes, task))
        await asyncio.wait(
            [task for _, _, task in tasks],
            return_when=asyncio.ALL_COMPLETED
        )

        texts = []
        for c, mes, task in tasks:
            if mes.result:
                texts.append(f'[{client.name(c.user)}] {mes.result}')
        await message.reply('\n\n'.join(texts))

    @command(
        name='restart',
        usage='{name}'
    )
    async def restart(command: Command, client: 'Client', message: MyMessage) -> None:
        await message.reply(
            client.l('restarting')
        )
        await asyncio.sleep(1)
        await client.bot.reboot()

    @command(
        name='relogin',
        usage='{name}'
    )
    async def relogin(command: Command, client: 'Client', message: MyMessage) -> None:
        await message.reply(
            client.l('relogining')
        )
        await asyncio.sleep(1)
        await client.restart()
        await message.reply('done')

    @command(
        name='reload',
        usage='{name}'
    )
    async def reload(command: Command, client: 'Client', message: MyMessage) -> None:
        config, error_config = client.bot.load_config()
        if config is None and error_config is None:
            await message.reply(
                client.l('failed_to_load_config')
            )
            return
        if error_config:
            client.send(
                client.bot.l(
                    'error_keys',
                    '\n'.join(error_config),
                    default=(
                        "以下のキーに問題がありました\n{0}\n"
                        "There was an error on keys\n{0}\n"
                    )
                ),
                file=sys.stderr
            )
            await message.reply(
                client.l('failed_to_load_config')
            )
            return

        try:
            client_config = config['clients'][client.num]
        except IndexError:
            await message.reply(
                client.l('failed_to_load_config_index')
            )
            return

        client.bot.config['clients'][client.num].clear()
        client.bot.config['clients'][client.num].update(client_config)
        client.bot.fix_config(client.config)
        ret = await client.ready_init()
        if not ret:
            await message.reply(
                client.l('failed_to_load_config_init')
            )
            return
        await message.reply(
            client.l('load_config_success')
        )

        if client.config['fortnite']['refresh_on_reload']:
            coros = []

            items = [
                'AthenaCharacter',
                'AthenaBackpack',
                'AthenaPickaxe',
                'AthenaDance'
            ]
            for item in items:
                conf = client.bot.convert_backend_type(item)
                variants = []
                if item != 'AthenaDance' and client.config['fortnite'][f'{conf}_style'] is not None:
                    for style in client.config['fortnite'][f'{conf}_style']:
                        variant = client.get_config_variant(style)
                        if variant is not None:
                            variants.extend(variant['variants'])
                coro = client.party.me.change_asset(
                    item,
                    (client.get_config_item_id(client.config['fortnite'][conf])
                     or client.config['fortnite'][conf]),
                    variants=variants
                )
                coro.__qualname__ = f'ClientPartyMember.set_{conf}'
                coros.append(coro)
            await client.party.me.edit(
                *coros
            )

        commands, error_commands = client.bot.load_commands()
        if commands is None and error_commands is None:
            await message.reply(
                client.l('failed_to_load_commands')
            )
            return
        if error_commands:
            client.send(
                client.bot.l(
                    'error_keys',
                    '\n'.join(error_commands),
                    default=(
                        "以下のキーに問題がありました\n{0}\n"
                        "There was an error on keys\n{0}\n"
                    )
                ),
                file=sys.stderr
            )
            await message.reply(
                client.l('failed_to_load_config')
            )
            return

        client.commands = commands
        client.error_commands = error_commands

        await message.reply(
            client.l('load_commands_success')
        )

    @command(
        name='reload_all',
        usage='{name}'
    )
    async def reload_all(command: Command, client: 'Client', message: MyMessage) -> None:
        config, error_config = client.bot.load_config()
        if config is None and error_config is None:
            await message.reply(
                client.l('failed_to_load_config')
            )
            return
        if error_config:
            client.send(
                client.bot.l(
                    'error_keys',
                    '\n'.join(error_config),
                    default=(
                        "以下のキーに問題がありました\n{0}\n"
                        "There was an error on keys\n{0}\n"
                    )
                ),
                file=sys.stderr
            )
            await message.reply(
                client.l('failed_to_load_config')
            )
            return

        client.bot.config.clear()
        client.bot.config.update(config)
        client.bot.error_config = error_config
        client.bot.fix_config_all()
        for c in client.bot.clients:
            try:
                ret = await c.ready_init()
                if not ret:
                    await message.reply(
                        c.l('failed_to_load_config_init')
                    )
                    return

                if c.config['fortnite']['refresh_on_reload']:
                    coros = []

                    items = [
                        'AthenaCharacter',
                        'AthenaBackpack',
                        'AthenaPickaxe',
                        'AthenaDance'
                    ]
                    for item in items:
                        conf = c.bot.convert_backend_type(item)
                        variants = []
                        if item != 'AthenaDance' and c.config['fortnite'][f'{conf}_style'] is not None:
                            for style in c.config['fortnite'][f'{conf}_style']:
                                variant = c.get_config_variant(style)
                                if variant is not None:
                                    variants.extend(variant['variants'])
                        coro = c.party.me.change_asset(
                            item,
                            (c.get_config_item_id(c.config['fortnite'][conf])
                             or c.config['fortnite'][conf]),
                            variants=variants
                        )
                        coro.__qualname__ = f'ClientPartyMember.set_{conf}'
                        coros.append(coro)
                    await c.party.me.edit(
                        *coros
                    )
            except IndexError as e:
                client.debug_print_exception(e)

        client.bot.save_json('config', config)

        await message.reply(
            client.l('load_config_success')
        )

        commands, error_commands = client.bot.load_commands()
        if commands is None and error_commands is None:
            await message.reply(
                client.l('failed_to_load_commands')
            )
            return
        if error_commands:
            client.send(
                client.bot.l(
                    'error_keys',
                    '\n'.join(error_commands),
                    default=(
                        "以下のキーに問題がありました\n{0}\n"
                        "There was an error on keys\n{0}\n"
                    )
                ),
                file=sys.stderr
            )
            await message.reply(
                client.l('failed_to_load_config')
            )
            return

        client.bot.commands = commands
        client.bot.error_commands = error_commands
        for client in client.bot.clients:
            client.commands = commands

        await message.reply(
            client.l('load_commands_success')
        )

    @command(
        name='add_blacklist',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def add_blacklist(command: Command, client: 'Client', message: MyMessage) -> None:
        await list_operation(add_to_list, 'blacklist', command, client, message)

    @command(
        name='remove_blacklist',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def remove_blacklist(command: Command, client: 'Client', message: MyMessage) -> None:
        await list_operation(remove_from_list, 'blacklist', command, client, message)

    @command(
        name='add_whitelist',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def add_whitelist(command: Command, client: 'Client', message: MyMessage) -> None:
        await list_operation(add_to_list, 'whitelist', command, client, message)

    @command(
        name='remove_whitelist',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def remove_whitelist(command: Command, client: 'Client', message: MyMessage) -> None:
        await list_operation(remove_from_list, 'whitelist', command, client, message)

    @command(
        name='add_invitelist',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def add_invitelist(command: Command, client: 'Client', message: MyMessage) -> None:
        await list_operation(add_to_list, 'invitelist', command, client, message)

    @command(
        name='remove_invitelist',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def remove_invitelist(command: Command, client: 'Client', message: MyMessage) -> None:
        await list_operation(remove_from_list, 'invitelist', command, client, message)

    @command(
        name='get_user',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def get_user(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            me=message.author
        )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        else:
            text = '\n'.join([client.name(user) for user in users])
            client.send(text)
            await message.reply(text)

    @command(
        name='get_friend',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def get_friend(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.friends,
            me=message.author
        )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        else:
            text = ''
            for user in users:
                friend = client.get_friend(user.id)
                if friend is None:
                    continue

                text += (
                    f'{client.name(friend)}: '
                    f'{client.l("online") if friend.is_online() else client.l("offline")}\n'
                )
                if friend.last_presence and friend.last_presence.avatar:
                    text += client.l(
                        'avatar_info',
                        friend.last_presence.avatar.asset
                    ) + '\n'
                if friend.last_logout:
                    text += client.l(
                        'last_logout_info',
                        friend.last_logout
                    ) + '\n'
            client.send(text)
            await message.reply(text)

    @command(
        name='get_pending',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def get_pending(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.pending_friends,
            me=message.author
        )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        else:
            text = ''

            outgoings = [user for user in users if client.is_outgoing_pending(user.id)]
            text += client.l('outgoing_pending') + '\n'
            text += '\n'.join([client.name(outgoing) for outgoing in outgoings])

            incomings = [user for user in users if client.is_incoming_pending(user.id)]
            text += client.l('incoming_pending') + '\n'
            text += '\n'.join([client.name(incoming) for incoming in incomings])

            client.send(text)
            await message.reply(text)

    @command(
        name='get_block',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def get_block(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.blocked_users,
            me=message.author
        )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        else:
            text = '\n'.join([client.name(user) for user in users])
            client.send(text)
            await message.reply(text)

    @command(
        name='get_member',
        usage='{name} [{client.l("name_or_id)}]'
    )
    async def get_member(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.party.members,
            me=message.author
        )

        async def get_member(user):
            member = client.party.get_member(user.id)
            if member is None:
                await message.reply(
                    client.l(
                        'not_found',
                        client.l('party_member'),
                        client.name(user)
                    )
                )
                return

            text = (f'{client.name(member)}\n'
                    f'CID: {client.asset("AthenaCharacter", member)} {member.outfit_variants}\n'
                    f'BID: {client.asset("AthenaBackpack", member)} {member.backpack_variants}\n'
                    f'Pickaxe_ID: {client.asset("AthenaPickaxe", member)} {member.pickaxe_variants}\n'
                    f'EID: {client.asset("AthenaDance", member)}\n')
            client.send(text)
            if client.config['loglevel'] == 'debug':
                client.send(
                    json.dumps(member.meta.schema, indent=4, ensure_ascii=False),
                    color=yellow,
                    add_p=client.time,
                    add_d=client.debug_message
                )
            await message.reply(text)

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await get_member(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await get_member(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='friend_count',
        usage='{name}'
    )
    async def friend_count(command: Command, client: 'Client', message: MyMessage) -> None:
        await message.reply(
            client.l('friend_count_info', len(client.friends))
        )

    @command(
        name='pending_count',
        usage='{name}'
    )
    async def pending_count(command: Command, client: 'Client', message: MyMessage) -> None:
        await message.reply(
            client.l(
                'pending_count_info',
                len(client.pending_friends),
                len(client.outgoing_pending_friends),
                len(client.incoming_pending_friends)
            )
        )

    @command(
        name='block_count',
        usage='{name}'
    )
    async def block_count(command: Command, client: 'Client', message: MyMessage) -> None:
        await message.reply(
            client.l('block_count_info', len(client.block_users))
        )

    @command(
        name='friend_list',
        usage='{name}'
    )
    async def friend_list(command: Command, client: 'Client', message: MyMessage) -> None:
        await message.reply(
            client.l(
                'friend_list_info',
                len(client.friends),
                '\n'.join([client.name(user) for user in client.friends])
            )
        )

    @command(
        name='pending_list',
        usage='{name}'
    )
    async def pending_list(command: Command, client: 'Client', message: MyMessage) -> None:
        await message.reply(
            client.l(
                'pending_list_info',
                len(client.outgoing_pending_friends),
                len(client.incoming_pending_friends),
                '\n'.join([client.name(user) for user in client.outgoing_pending_friends]),
                '\n'.join([client.name(user) for user in client.incoming_pending_friends])
            )
        )

    @command(
        name='block_list',
        usage='{name}'
    )
    async def block_list(command: Command, client: 'Client', message: MyMessage) -> None:
        await message.reply(
            client.l(
                'block_list_info',
                len(client.blocked_users),
                '\n'.join([client.name(user) for user in client.blocked_users])
            )
        )

    @command(
        name='add_friend',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def add_friend(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            me=message.author
        )

        async def add_friend(user):
            if client.has_friend(user.id):
                await message.reply(
                    client.l(
                        'already_friend_with_user',
                        client.name(user)
                    )
                )
                return

            ret = await client.send_friend_request(user, message)
            if not isinstance(ret, Exception):
                await message.reply(
                    client.l(
                        'add_friend',
                        client.name(user)
                    )
                )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await add_friend(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await add_friend(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='remove_friend',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def remove_friend(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.friends,
            me=message.author
        )

        async def remove_friend(user):
            friend = client.get_friend(user.id)
            if friend is None:
                await message.reply(
                    client.l(
                        'not_friend_with_user',
                        client.name(user)
                    )
                )
                return

            ret = await client.remove_friend(friend, message)
            if not isinstance(ret, Exception):
                await message.reply(
                    client.l(
                        'remove_friend',
                        client.name(friend)
                    )
                )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await remove_friend(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await remove_friend(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='remove_friends',
        usage='{name} [{client.num("number")}]'
    )
    async def remove_friends(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        try:
            number = int(message.args[1])
        except ValueError as e:
            client.debug_print_exception(e)
            await message.reply(
                client.l('please_enter_valid_number')
            )
            return

        random_friends = random.sample(client.friends, k=number)

        async def remove_friends():
            friend_count_before = len(client.friends)
            for friend in random_friends:
                await client.remove_friend(friend, message)
            friend_count_after = len(client.friends)
            await message.reply(
                client.l(
                    'remove_friends',
                    friend_count_before - friend_count_after
                )
            )

        task = client.loop.create_task(remove_friends())
        client.stoppable_tasks.append(task)

    @command(
        name='remove_all_friend',
        usage='{name}'
    )
    async def remove_all_friend(command: Command, client: 'Client', message: MyMessage) -> None:
        async def remove_all_friend():
            friend_count_before = len(client.friends)
            for friend in client.friends:
                await client.remove_friend(friend, message)
            friend_count_after = len(client.friends)
            await message.reply(
                client.l(
                    'remove_friends',
                    friend_count_before - friend_count_after
                )
            )

        task = client.loop.create_task(remove_all_friend())
        client.stoppable_tasks.append(task)

    @command(
        name='remove_offline_for',
        usage='{name} [{client.l("day")}] ({client.l("hour")}) ({client.l("minute")})'
    )
    async def remove_offline_for(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        kwargs = {
            'days': message.args[1],
            'hours': client.bot.get_list_index(message.args, 2, 0),
            'minutes': client.bot.get_list_index(message.args, 3, 0)
        }
        offline_for = datetime.timedelta(**kwargs)
        utcnow = datetime.datetime.utcnow()
        friend_count_before = len(client.friends)

        async def remove(friend):
            last_logout = None
            if friend.last_logout is not None:
                last_logout = friend.last_logout
            if friend.last_logout is None or (friend.created_at > client.booted_at):
                last_logout = await friend.fetch_last_logout()

            if last_logout is not None and ((utcnow - last_logout) >= offline_for):
                await client.remove_friend(friend, message)

        tasks = [client.loop.create_task(remove(friend)) for friend in client.friends]
        await asyncio.wait(
            tasks,
            return_when=asyncio.ALL_COMPLETED
        )

        friend_count_after = len(client.friends)
        await message.reply(
            client.l(
                'remove_friends',
                friend_count_before - friend_count_after
            )
        )

    @command(
        name='accept_pending',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def accept_pending(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.incoming_pending_friends,
            me=message.author
        )

        async def accept_pending(user):
            ret = await client.accept_request(user, message)
            if not isinstance(ret, Exception):
                await message.reply(
                    client.l(
                        'accept_pending',
                        client.name(user)
                    )
                )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await accept_pending(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await accept_pending(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='decline_pending',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def decline_pending(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.incoming_pending_friends,
            me=message.author
        )

        async def decline_pending(user):
            ret = await client.decline_request(user, message)
            if not isinstance(ret, Exception):
                await message.reply(
                    client.l(
                        'decline_pending',
                        client.name(user)
                    )
                )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await decline_pending(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await decline_pending(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='incoming_pending',
        usage='{name} [{client.l("bool", **self.variables_without_self)}]'
    )
    async def incoming_pending(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        count_before = len(client.incoming_pending_friends)
        if message.args[1] in client.commands['accept']:
            async def incoming_pending():
                for pending in client.incoming_pending_friends:
                    await client.accept_request(pending, message)
                count_after = len(client.incoming_pending_friends)
                await message.reply(
                    client.l(
                        'accept_pendings',
                        count_before - count_after
                    )
                )

            task = client.loop.create_task(incoming_pending())
            client.stoppable_tasks.append(task)
        elif message.args[1] in client.commands['decline']:
            async def incoming_pending():
                for pending in client.incoming_pending_friends:
                    await client.decline_request(pending, message)
                count_after = len(client.incoming_pending_friends)
                await message.reply(
                    client.l(
                        'decline_pendings',
                        count_before - count_after
                    )
                )

            task = client.loop.create_task(incoming_pending())
            client.stoppable_tasks.append(task)
        else:
            await client.show_help(command, message)

    @command(
        name='cancel_outgoing_pending',
        usage='{name}'
    )
    async def cancel_outgoing_pending(command: Command, client: 'Client', message: MyMessage) -> None:
        async def cancel_outgoing_pending():
            count_before = len(client.outgoing_pending_friends)
            for pending in client.outgoing_pending_friends:
                await client.decline_request(pending, message)
            count_after = len(client.outgoing_pending_friends)
            await message.reply(
                client.l(
                    'remov_pendings',
                    count_before - count_after
                )
            )

        task = client.loop.create_task(cancel_outgoing_pending())
        client.stoppable_tasks.append(task)

    @command(
        name='block_user',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def block_user(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.incoming_pending_friends,
            me=message.author
        )

        async def block_user(user):
            if client.is_blocked(user.id):
                await message.reply(
                    client.l(
                        'already_blocked',
                        client.name(user)
                    )
                )

            ret = await client.block_user(user, message)
            if not isinstance(ret, Exception):
                await message.reply(
                    client.l(
                        'block_user',
                        client.name(user)
                    )
                )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await block_user(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await block_user(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='unblock_user',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def unblock_user(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.incoming_pending_friends,
            me=message.author
        )

        async def unblock_user(user):
            blocked_user = client.get_blocked_user(user.id)
            if blocked_user is None:
                await message.reply(
                    client.l(
                        'not_blocking_user',
                        client.name(user)
                    )
                )

            ret = await client.unblock_user(blocked_user, message)
            if not isinstance(ret, Exception):
                await message.reply(
                    client.l(
                        'unblock_user',
                        client.name(blocked_user)
                    )
                )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await unblock_user(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await unblock_user(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='unblock_all_user',
        usage='{name}'
    )
    async def unblock_all_user(command: Command, client: 'Client', message: MyMessage) -> None:
        async def unblock_all_user():
            block_count_before = len(client.blocked_users)
            for blocked_user in client.blocked_users:
                await client.unblock_user(blocked_user)
            block_count_after = len(client.blocked_users)
            await message.reply(
                client.l(
                    'unblock_users',
                    block_count_before - block_count_after
                )
            )

        task = client.loop.create_task(unblock_all_user())
        client.stoppable_tasks.append(task)

    @command(
        name='join',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def join(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.friends,
            me=message.author
        )

        async def join(user):
            friend = client.get_friend(user.id)
            if friend is None:
                await message.reply(
                    client.l(
                        'not_friend_with_user',
                        client.name(user)
                    )
                )
                return

            ret = await client.join_party_friend(friend, message)
            if not isinstance(ret, Exception):
                if client.config['loglevel'] == 'normal':
                    await message.reply(
                        client.l(
                            'party_join_friend',
                            client.name(friend)
                        )
                    )
                else:
                    await message.reply(
                        client.l(
                            'party_join_friend_info',
                            client.name(friend),
                            ret.id
                        )
                    )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await join(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await join(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='join_id',
        usage='{name} [{client.l("party_id")}]'
    )
    async def join_id(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        ret = await client.join_party_id(message.args[1], message)
        if not isinstance(ret, Exception):
            if client.config['loglevel'] == 'normal':
                await message.reply(
                    client.l('party_join')
                )
            else:
                await message.reply(
                    client.l(
                        'party_join_info',
                        ret.id
                    )
                )

    @command(
        name='leave',
        usage='{name}'
    )
    async def leave(command: Command, client: 'Client', message: MyMessage) -> None:
        await client.party.me.leave()
        if client.config['loglevel'] == 'normal':
            await message.reply(
                client.l('party_leave')
            )
        else:
            await message.reply(
                client.l(
                    'party_leave_info',
                    client.party.id
                )
            )

    @command(
        name='invite',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def invite(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.friends,
            me=message.author
        )

        async def invite(user):
            friend = client.get_friend(user.id)
            if friend is None:
                await message.reply(
                    client.l(
                        'not_friend_with_user',
                        client.name(user)
                    )
                )
                return

            ret = await client.invite_friend(friend, message)
            if not isinstance(ret, Exception):
                if client.config['loglevel'] == 'normal':
                    await message.reply(
                        client.l(
                            'user_invite',
                            client.name(friend)
                        )
                    )
                else:
                    await message.reply(
                        client.l(
                            'user_invite_info',
                            client.name(friend),
                            client.party.id
                        )
                    )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await invite(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await invite(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='invite_list_users',
        usage='{name}'
    )
    async def invite_list_users(command: Command, client: 'Client', message: MyMessage) -> None:
        users = [user for user in client.invitelist
                 if isinstance(user, fortnitepy.Friend)]
        if len(users) == 0:
            return

        tasks = [
            client.loop.create_task(client.invite_friend(user, message))
            for user in users
        ]
        await asyncio.wait(
            tasks,
            return_when=asyncio.ALL_COMPLETED
        )
        if client.config['loglevel'] == 'normal':
            await message.reply(
                client.l('invitelist_invite')
            )
        else:
            await message.reply(
                client.l(
                    'invitelist_invite_info',
                    client.party.id
                )
            )

    @command(
        name='message',
        usage='{name} [{client.l("name_or_id")}] : [{client.l("message")}]'
    )
    async def message(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        text = ' '.join(message.args[1:]).split(' : ')
        if len(text) < 2:
            await client.show_help(command, message)
            return

        user_name, content = text

        users = client.find_users(
            user_name,
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.friends,
            me=message.author
        )

        async def message(user):
            friend = client.get_friend(user.id)
            if friend is None:
                await message.reply(
                    client.l(
                        'not_friend_with_user',
                        client.name(user)
                    )
                )
                return

            await friend.send(content)
            await message.reply(
                client.l(
                    'sent_message',
                    client.name(friend),
                    content
                )
            )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    user_name
                )
            )
        elif len(users) == 1:
            await message(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await message(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='party_message',
        usage='{name} [{client.l("message")}]'
    )
    async def party_message(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        await client.party.send(
            ' '.join(message.args[1:])
        )
        if client.config['loglevel'] == 'normal':
            await message.reply(
                client.l(
                    'sent_party_message',
                    ' '.join(message.args[1:])
                )
            )
        else:
            await message.reply(
                client.l(
                    'sent_party_message_info',
                    ' '.join(message.args[1:]),
                    client.party.id
                )
            )

    @command(
        name='avatar',
        usage='{name} [ID] ({client.l("color")})'
    )
    async def avatar(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        if len(message.args) >= 5:
            background_colors = message.args[2:4]
        elif len(message.args) == 2:
            background_colors = None
        else:
            try:
                background_colors = getattr(
                    fortnitepy.KairosBackgroundColorPreset,
                    message.args[2].upper()
                )
            except AttributeError as e:
                client.debug_print_exception(e)
                await message.reply(
                    client.l(
                        'must_be_one_of',
                        client.l('color'),
                        [i.name for i in fortnitepy.KairosBackgroundColorPreset]
                    )
                )
                return

        avatar = fortnitepy.Avatar(
            asset=message.args[1],
            background_colors=background_colors
        )
        client.set_avatar(avatar)
        await message.reply(
            client.l(
                'set_to',
                client.l('avatar'),
                f'{message.args[1]}, {background_colors}'
            )
        )

    @command(
        name='status',
        usage='{name} [{client.l("message")}]'
    )
    async def status(command: Command, client: 'Client', message: MyMessage) -> None:
        await client.set_presence(' '.join(message.args[1:]))
        await message.reply(
            client.l(
                'set_to',
                client.l('status'),
                ' '.join(message.args[1:])
            )
        )

    @command(
        name='banner',
        usage='{name} [ID] [{client.l("color")}]'
    )
    async def banner(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 3:
            await client.show_help(command, message)
            return

        await client.party.me.edit_and_keep(partial(
            client.party.me.set_banner,
            icon=message.args[1],
            color=message.args[2],
            season_level=client.party.me.banner[2]
        ))
        await message.reply(
            client.l(
                'set_to',
                client.l('banner'),
                f"{message.args[1]}, {message.args[2]}"
            )
        )

    @command(
        name='level',
        usage='{name} [{client.l("number")}]'
    )
    async def level(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        icon, color = client.party.me.banner[:2]
        try:
            level = int(message.args[1])
        except ValueError as e:
            client.debug_print_exception(e)
            await message.reply(
                client.l('please_enter_valid_value')
            )
            return
        await client.party.me.edit_and_keep(partial(
            client.party.me.set_banner,
            icon=icon,
            color=color,
            season_level=level
        ))
        await message.reply(
            client.l(
                'set_to',
                client.l('level'),
                level
            )
        )

    @command(
        name='privacy',
        usage='{name} [{client.l("privacy")}]'
    )
    async def privacy(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        if not client.party.me.leader:
            await message.reply(
                client.l('not_a_party_leader')
            )

        privacies = [
            (p.name.lower(), p) for p in PartyPrivacy
        ]
        for p, value in privacies:
            if message.args[1] in client.commands[p]:
                try:
                    await client.party.set_privacy(value)
                except fortnitepy.Forbidden as e:
                    client.debug_print_exception(e)
                    await message.reply(
                        client.l('not_a_party_leader')
                    )
                    return
                await message.reply(
                    client.l(
                        'set_to',
                        client.l('privacy'),
                        client.bot.l(f'privacy_{p}')
                    )
                )
                break
        else:
            await message.reply(
                client.l(
                    'must_be_one_of',
                    client.l('privacy'),
                    [client.commands[p][0] for p in privacies]
                )
            )

    @command(
        name='voice_chat',
        usage=(
            '{name} [{client.l("bool", **self.variables_without_self)}]\n'
            '{client.l("current_setting", client.l("enabled") '
            'if client.party.voice_chat_enabled else '
            'client.l("disabled"))}'
        )
    )
    async def voice_chat(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        if not client.party.me.leader:
            await message.reply(
                client.l('not_a_party_leader')
            )
            return

        if message.args[1] in client.commands['true']:
            try:
                await client.party.enable_voice_chat()
            except fortnitepy.Forbidden as e:
                client.debug_print_exception(e)
                await message.reply(
                    client.l('not_a_party_leader')
                )
                return
            await message.reply(
                client.l(
                    'set_to',
                    client.l('voice_chat'),
                    client.l('enabled')
                )
            )
        elif message.args[1] in client.commands['false']:
            try:
                await client.party.disable_voice_chat()
            except fortnitepy.Forbidden as e:
                client.debug_print_exception(e)
                await message.reply(
                    client.l('not_a_party_leader')
                )
                return
            await message.reply(
                client.l(
                    'set_to',
                    client.l('voice_chat'),
                    client.l('disabled')
                )
            )
        else:
            await client.show_help(command, message)

    @command(
        name='promote',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def promote(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        if not client.party.me.leader:
            await message.reply(
                client.l('not_a_party_leader')
            )
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.party.members,
            me=message.author
        )

        async def promote(user):
            member = client.party.get_member(user.id)
            if member is None:
                await message.reply(
                    client.l(
                        'not_in_party',
                        client.name(user)
                    )
                )
                return

            ret = await client.promote_member(member, message)
            if not isinstance(ret, Exception):
                await message.reply(
                    client.l(
                        'promote',
                        client.name(member)
                    )
                )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await promote(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await promote(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='kick',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def kick(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        if not client.party.me.leader:
            await message.reply(
                client.l('not_a_party_leader')
            )
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.party.members,
            me=message.author
        )

        async def kick(user):
            member = client.party.get_member(user.id)
            if member is None:
                await message.reply(
                    client.l(
                        'not_in_party',
                        client.name(user)
                    )
                )
                return

            ret = await client.kick_member(member, message)
            if not isinstance(ret, Exception):
                await message.reply(
                    client.l(
                        'kick',
                        client.name(member)
                    )
                )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await kick(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await kick(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='chatban',
        usage='{name} [{client.l("name_or_id")}] : ({client.l("reason")})'
    )
    async def chatban(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        if not client.party.me.leader:
            await message.reply(
                client.l('not_a_party_leader')
            )
            return

        text = ' '.join(message.args[1:]).split(' : ')

        if len(text) == 1:
            user_name = text[0]
            reason = None
        else:
            user_name, *reason = text
            reason = ' '.join(reason)

        users = client.find_users(
            user_name,
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.party.members,
            me=message.author
        )

        async def chatban(user):
            member = client.party.get_member(user.id)
            if member is None:
                await message.reply(
                    client.l(
                        'not_in_party',
                        client.name(user)
                    )
                )
                return

            ret = await client.chatban_member(member, reason, message)
            if not isinstance(ret, Exception):
                if reason is None:
                    await message.reply(
                        client.l(
                            'chatban',
                            client.name(member)
                        )
                    )
                else:
                    await message.reply(
                        client.l(
                            'chatban_reason',
                            client.name(member),
                            reason
                        )
                    )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    user_name
                )
            )
        elif len(users) == 1:
            await chatban(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await chatban(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='hide',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def hide(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            count = 0
            for member in client.party.members:
                if client.is_hide_for(member.id):
                    client.party.add_hide_user(member.id)
                    count += 1
            try:
                await client.party.refresh_squad_assignments()
            except Exception as e:
                if isinstance(e, fortnitepy.HTTPException):
                    client.debug_print_exception(e)
                else:
                    client.print_exception(e)
                text = client.l('error_while_hiding_members')
                client.send(
                    text,
                    add_p=client.time,
                    file=sys.stderr
                )
                if message is not None:
                    await message.reply(text)
                return
            await message.reply(
                client.l(
                    'hide_members',
                    count
                )
            )
        else:
            if not client.party.me.leader:
                await message.reply(
                    client.l('not_a_party_leader')
                )
                return

            users = client.find_users(
                ' '.join(message.args[1:]),
                mode=FindUserMode.NAME_ID,
                method=FindUserMatchMethod.CONTAINS,
                users=client.party.members,
                me=message.author
            )

            async def hide(user):
                member = client.party.get_member(user.id)
                if member is None:
                    await message.reply(
                        client.l(
                            'not_in_party',
                            client.name(user)
                        )
                    )
                    return

                ret = await client.hide_member(member, message)
                if not isinstance(ret, Exception):
                    await message.reply(
                        client.l(
                            'hide',
                            client.name(member)
                        )
                    )

            if len(users) > client.config['search_max']:
                await message.reply(
                    client.l('too_many', client.l('user'), len(users))
                )
                return

            if len(users) == 0:
                await message.reply(
                    client.l(
                        'not_found',
                        client.l('user'),
                        ' '.join(message.args[1:])
                    )
                )
            elif len(users) == 1:
                await hide(users[0])
            else:
                client.select[message.author.id] = {
                    'exec': 'await hide(user)',
                    'globals': {**globals(), **locals()},
                    'variables': [
                        {'user': user}
                        for user in users
                    ]
                }
                await message.reply(
                    ('\n'.join([f'{num}: {client.name(user)}'
                                for num, user in enumerate(users, 1)])
                        + '\n' + client.l('enter_number_to_select', client.l('user')))
                )

    @command(
        name='show',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def show(command: Command, client: 'Client', message: MyMessage) -> None:
        if not client.party.me.leader:
            await message.reply(
                client.l('not_a_party_leader')
            )
            return

        if len(message.args) < 2:
            for member in client.party.members:
                client.party.remove_hide_user(member.id)
            try:
                await client.party.refresh_squad_assignments()
            except Exception as e:
                if isinstance(e, fortnitepy.HTTPException):
                    client.debug_print_exception(e)
                else:
                    client.print_exception(e)
                text = client.l('error_while_showing_members')
                client.send(
                    text,
                    add_p=client.time,
                    file=sys.stderr
                )
                if message is not None:
                    await message.reply(text)
                return
            await message.reply(
                client.l(
                    'show_members',
                    len(client.party.members)
                )
            )
        else:
            users = client.find_users(
                ' '.join(message.args[1:]),
                mode=FindUserMode.NAME_ID,
                method=FindUserMatchMethod.CONTAINS,
                users=client.party.members,
                me=message.author
            )

            async def show(user):
                member = client.party.get_member(user.id)
                if member is None:
                    await message.reply(
                        client.l(
                            'not_in_party',
                            client.name(user)
                        )
                    )
                    return

                ret = await client.show_member(member, message)
                if not isinstance(ret, Exception):
                    await message.reply(
                        client.l(
                            'show',
                            client.name(member)
                        )
                    )

            if len(users) > client.config['search_max']:
                await message.reply(
                    client.l('too_many', client.l('user'), len(users))
                )
                return

            if len(users) == 0:
                await message.reply(
                    client.l(
                        'not_found',
                        client.l('user'),
                        ' '.join(message.args[1:])
                    )
                )
            elif len(users) == 1:
                await show(users[0])
            else:
                client.select[message.author.id] = {
                    'exec': 'await show(user)',
                    'globals': {**globals(), **locals()},
                    'variables': [
                        {'user': user}
                        for user in users
                    ]
                }
                await message.reply(
                    ('\n'.join([f'{num}: {client.name(user)}'
                                for num, user in enumerate(users, 1)])
                        + '\n' + client.l('enter_number_to_select', client.l('user')))
                )

    @command(
        name='ready',
        usage='{name}'
    )
    async def ready(command: Command, client: 'Client', message: MyMessage) -> None:
        await client.party.me.set_ready(fortnitepy.ReadyState.READY)
        await message.reply(
            client.l(
                'set_to',
                client.l('ready_state'),
                client.l('ready_state_ready')
            )
        )

    @command(
        name='unready',
        usage='{name}'
    )
    async def unready(command: Command, client: 'Client', message: MyMessage) -> None:
        await client.party.me.set_ready(fortnitepy.ReadyState.NOT_READY)
        await message.reply(
            client.l(
                'set_to',
                client.l('ready_state'),
                client.l('ready_state_unready')
            )
        )

    @command(
        name='sitout',
        usage='{name}'
    )
    async def sitout(command: Command, client: 'Client', message: MyMessage) -> None:
        await client.party.me.set_ready(fortnitepy.ReadyState.SITTING_OUT)
        await message.reply(
            client.l(
                'set_to',
                client.l('ready_state'),
                client.l('ready_state_sitout')
            )
        )

    @command(
        name='match',
        usage='{name} ({client.l("number")})'
    )
    async def match(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            players_left = 100
        else:
            try:
                players_left = int(message.args[1])
            except ValueError as e:
                client.debug_print_exception(e)
                await message.reply(
                    client.l('please_enter_valid_number')
                )
                return

        await client.party.me.set_in_match(
            players_left=players_left
        )
        await message.reply(
            client.l(
                'set_to',
                client.l('match_state'),
                client.l(
                    'players_left',
                    players_left
                )
            )
        )

    @command(
        name='unmatch',
        usage='{name}'
    )
    async def unmatch(command: Command, client: 'Client', message: MyMessage) -> None:
        await client.party.me.clear_in_match()
        await message.reply(
            client.l(
                'set_to',
                client.l('match_state'),
                client.l('off')
            )
        )

    @command(
        name='swap',
        usage='{name} [{client.l("name_or_id")}]'
    )
    async def swap(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        users = client.find_users(
            ' '.join(message.args[1:]),
            mode=FindUserMode.NAME_ID,
            method=FindUserMatchMethod.CONTAINS,
            users=client.party.members,
            me=message.author
        )

        async def swap(user):
            member = client.party.get_member(user.id)
            if member is None:
                await message.reply(
                    client.l(
                        'not_in_party',
                        client.name(user)
                    )
                )
                return

            ret = await client.swap_member(member, message)
            if not isinstance(ret, Exception):
                await message.reply(
                    client.l(
                        'swap',
                        client.name(member)
                    )
                )

        if len(users) > client.config['search_max']:
            await message.reply(
                client.l('too_many', client.l('user'), len(users))
            )
            return

        if len(users) == 0:
            await message.reply(
                client.l(
                    'not_found',
                    client.l('user'),
                    ' '.join(message.args[1:])
                )
            )
        elif len(users) == 1:
            await swap(users[0])
        else:
            client.select[message.author.id] = {
                'exec': 'await swap(user)',
                'globals': {**globals(), **locals()},
                'variables': [
                    {'user': user}
                    for user in users
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {client.name(user)}'
                            for num, user in enumerate(users, 1)])
                    + '\n' + client.l('enter_number_to_select', client.l('user')))
            )

    @command(
        name='stop',
        usage='{name}'
    )
    async def stop(command: Command, client: 'Client', message: MyMessage) -> None:
        if not client.is_emote_lock_for(message.author.id):
            await client.party.me.clear_emote()
            await message.reply(
                client.l('stopped')
            )
            for num in reversed(range(len(client.stoppable_tasks))):
                exc = client.stoppable_tasks[num].exception()
                if exc is not None:
                    client.debug_print_exception(exc)
                client.stoppable_tasks[num].cancel()
                del client.stoppable_tasks[num]

        else:
            await message.reply(
                client.l('cosmetic_locked')
            )

    @command(
        name='new_items',
        usage='{name}'
    )
    async def new_items(command: Command, client: 'Client', message: MyMessage) -> None:
        async def new_items():
            for item in client.bot.new_items.values():
                attr = f'is_{client.bot.convert_backend_to_key(item["type"]["backendValue"])}_lock_for'
                if not getattr(client, attr)(message.author.id):
                    await client.party.me.change_asset(
                        item['type']['backendValue'],
                        item['id'],
                        keep=False
                    )
                    await message.reply(
                        f'{item["type"]["displayValue"]}: {client.name_cosmetic(item)}'
                    )
                    await asyncio.sleep(5)
                else:
                    await message.reply(
                        client.l('cosmetic_locked')
                    )
                    return
            await message.reply(
                client.l(
                    'has_end',
                    client.l('new_items')
                )
            )

        task = client.loop.create_task(new_items())
        client.stoppable_tasks.append(task)

    @command(
        name='shop_items',
        usage='{name}'
    )
    async def shop_items(command: Command, client: 'Client', message: MyMessage) -> None:
        async def shop_items():
            try:
                shop = await client.fetch_item_shop()
            except fortnitepy.HTTPException as e:
                m = 'errors.com.epicgames.common.missing_action'
                if e.message_code == m:
                    client.debug_print_exception(e)
                    await client.auth.accept_eula()
                    shop = await client.fetch_item_shop()
                else:
                    raise
            items = []
            entries = (sorted(shop.featured_items, key=lambda x: x.sort_priority, reverse=True)
                       + sorted(shop.daily_items, key=lambda x: x.sort_priority, reverse=True)
                       + sorted(shop.special_featured_items, key=lambda x: x.sort_priority, reverse=True)
                       + sorted(shop.special_daily_items, key=lambda x: x.sort_priority, reverse=True))
            for entry in entries:
                for item in entry.grants:
                    if item['type'] not in ['AthenaCharacter',
                                            'AthenaBackpack',
                                            'AthenaPet',
                                            'AthenaPetCarrier',
                                            'AthenaPickaxe',
                                            'AthenaDance',
                                            'AthenaEmoji',
                                            'AthenaToy']:
                        continue
                    items.append({
                        'name': client.bot.main_items.get(item['asset'], {}).get('name'),
                        'id': item['asset'],
                        'type': {
                            'value': client.bot.convert_backend_type(item['type']),
                            'displayValue': (
                                client.bot.l(
                                    client.bot.convert_backend_type(item['type'])
                                )
                                or client.bot.convert_backend_type(item['type'])
                            ),
                            'backendValue': item['type']
                        }
                    })
            for item in items:
                attr = f'is_{client.bot.convert_backend_to_key(item["type"]["backendValue"])}_lock_for'
                if not getattr(client, attr)(message.author.id):
                    await client.party.me.change_asset(
                        item['type']['backendValue'],
                        item['id'],
                        keep=False
                    )
                    await message.reply(
                        f'{item["type"]["displayValue"]}: {client.name_cosmetic(item)}'
                    )
                    await asyncio.sleep(5)

                else:
                    await message.reply(
                        client.l('cosmetic_locked')
                    )
            await message.reply(
                client.l(
                    'has_end',
                    client.l('shop_items')
                )
            )

        task = client.loop.create_task(shop_items())
        client.stoppable_tasks.append(task)

    @command(
        name='enlightenment',
        usage='{name} [{client.l("season")}] [{client.l("number")}]'
    )
    async def enlightenment(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 3:
            await client.show_help(command, message)
            return

        try:
            season = int(message.args[1])
            number = int(message.args[2])
        except ValueError as e:
            client.debug_print_exception(e)
            await message.reply(
                client.l('please_enter_valid_number')
            )
            return

        if not client.is_emote_lock_for(message.author.id):
            await client.party.me.change_asset(
                'AthenaCharacter',
                client.party.me.outfit,
                variants=client.party.me.outfit_variants,
                enlightenment=(season, number),
                corruption=client.party.me.corruption
            )
        else:
            await message.reply(
                client.l('cosmetic_locked')
            )

    @command(
        name='corruption',
        usage='{name} [{client.l("number")}]'
    )
    async def corruption(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        try:
            number = int(message.args[1])
        except ValueError as e:
            client.debug_print_exception(e)
            await message.reply(
                client.l('please_enter_valid_number')
            )
            return

        if not client.is_emote_lock_for(message.author.id):
            await client.party.me.change_asset(
                'AthenaCharacter',
                client.party.me.outfit,
                variants=client.party.me.outfit_variants,
                enlightenment=client.party.me.enlightenments,
                corruption=number
            )
        else:
            await message.reply(
                client.l('cosmetic_locked')
            )

    @command(
        name='all_outfit',
        usage='{name}'
    )
    async def all_outfit(command: Command, client: 'Client', message: MyMessage) -> None:
        await all_cosmetics('AthenaCharacter', client, message)

    @command(
        name='all_backpack',
        usage='{name}'
    )
    async def all_backpack(command: Command, client: 'Client', message: MyMessage) -> None:
        await all_cosmetics('AthenaBackpack', client, message)

    @command(
        name='all_pet',
        usage='{name}'
    )
    async def all_pet(command: Command, client: 'Client', message: MyMessage) -> None:
        await all_cosmetics('AthenaPet,AthenaPetCarrier', client, message)

    @command(
        name='all_pickaxe',
        usage='{name}'
    )
    async def all_pickaxe(command: Command, client: 'Client', message: MyMessage) -> None:
        await all_cosmetics('AthenaCharacter', client, message)

    @command(
        name='all_emote',
        usage='{name}'
    )
    async def all_emote(command: Command, client: 'Client', message: MyMessage) -> None:
        await all_cosmetics('AthenaDance', client, message)

    @command(
        name='all_emoji',
        usage='{name}'
    )
    async def all_emoji(command: Command, client: 'Client', message: MyMessage) -> None:
        await all_cosmetics('AthenaEmoji', client, message)

    @command(
        name='all_toy',
        usage='{name}'
    )
    async def all_toy(command: Command, client: 'Client', message: MyMessage) -> None:
        await all_cosmetics('AthenaToy', client, message)

    @command(
        name='cid',
        usage='{name} [ID]'
    )
    async def cid(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaCharacter', 'id', command, client, message)

    @command(
        name='bid',
        usage='{name} [ID]'
    )
    async def bid(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaBackpack', 'id', command, client, message)

    @command(
        name='petcarrier',
        usage='{name} [ID]'
    )
    async def petcarrier(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaPet,AthenaPetCarrier', 'id', command, client, message)

    @command(
        name='pickaxe_id',
        usage='{name} [ID]'
    )
    async def pickaxe_id(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaPickaxe', 'id', command, client, message)

    @command(
        name='eid',
        usage='{name} [ID]'
    )
    async def eid(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaDance', 'id', command, client, message)

    @command(
        name='emoji_id',
        usage='{name} [ID]'
    )
    async def emoji_id(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaEmoji', 'id', command, client, message)

    @command(
        name='toy_id',
        usage='{name} [ID]'
    )
    async def toy_id(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaToy', 'id', command, client, message)

    @command(
        name='id',
        usage='{name} [ID]'
    )
    async def id(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search(None, 'id', command, client, message)

    @command(
        name='outfit',
        usage='{name} [{client.l("name")}]'
    )
    async def outfit(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaCharacter', 'name', command, client, message)

    @command(
        name='backpack',
        usage='{name} [{client.l("name")}]'
    )
    async def backpack(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaBackpack', 'name', command, client, message)

    @command(
        name='pet',
        usage='{name} [{client.l("name")}]'
    )
    async def pet(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaPet,AthenaPetCarrier', 'name', command, client, message)

    @command(
        name='pickaxe',
        usage='{name} [{client.l("name")}]'
    )
    async def pickaxe(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaPickaxe', 'name', command, client, message)

    @command(
        name='emote',
        usage='{name} [{client.l("name")}]'
    )
    async def emote(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaDance', 'name', command, client, message)

    @command(
        name='emoji',
        usage='{name} [{client.l("name")}]'
    )
    async def emoji(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaEmoji', 'name', command, client, message)

    @command(
        name='toy',
        usage='{name} [{client.l("name")}]'
    )
    async def toy(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search('AthenaToy', 'name', command, client, message)

    @command(
        name='item',
        usage='{name} [{client.l("name")}]'
    )
    async def item(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search(None, 'name', command, client, message)

    @command(
        name='playlist_id',
        usage='{name} [ID]'
    )
    async def playlist_id(command: Command, client: 'Client', message: MyMessage) -> None:
        await playlist_search('id', command, client, message)

    @command(
        name='playlist',
        usage='{name} [{client.l("name")}]'
    )
    async def playlist(command: Command, client: 'Client', message: MyMessage) -> None:
        await playlist_search('name', command, client, message)

    @command(
        name='set',
        usage='{name} [{client.l("name")}]'
    )
    async def set_(command: Command, client: 'Client', message: MyMessage) -> None:
        await cosmetic_search(None, 'set', command, client, message)

    @command(
        name='set_style',
        usage='{name} [{client.l("cosmetic_types", **self.variables_without_self)}]'
    )
    async def set_style(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        if not any([message.args[1] in client.commands[key]
                    for key in ['outfit', 'backpack', 'pickaxe']]):
            await client.show_help(command, message)
            return

        for k in ['outfit', 'backpack', 'pickaxe']:
            if message.args[1] in client.commands[k]:
                key = k
                break
        else:
            return

        item = client.bot.convert_to_backend_type(key)
        asset = client.party.me.asset(item)
        enlightenment = client.party.me.enlightenments
        corruption = client.party.me.corruption
        styles = client.searcher.get_style(asset)

        async def set_style(style):
            attr = f'is_{client.bot.convert_backend_to_key(item)}_lock_for'
            if getattr(client, attr)(message.author.id):
                await message.reply(
                    client.l('cosmetic_locked')
                )
                return
            await client.party.me.change_asset(
                item,
                asset,
                variants=style['variants'],
                enlightenment=enlightenment,
                corruption=corruption
            )

        if len(styles) == 0:
            await message.reply(
                client.l('no_style_change')
            )
        else:
            client.select[message.author.id] = {
                'exec': (
                    'await set_style(style)'
                ),
                'globals': {**globals(), **locals()},
                'variables': [
                    {'style': style}
                    for style in styles
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {style["name"]}'
                            for num, style in enumerate(styles, 1)])
                    + '\n' + client.l('enter_number_to_select', client.bot.l('style')))
            )

    @command(
        name='add_style',
        usage='{name} [{client.l("cosmetic_types", **self.variables_without_self)}]'
    )
    async def add_style(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 2:
            await client.show_help(command, message)
            return

        if not any([message.args[1] in client.commands[key]
                    for key in ['outfit', 'backpack', 'pickaxe']]):
            await client.show_help(command, message)
            return

        for k in ['outfit', 'backpack', 'pickaxe']:
            if message.args[1] in client.commands[k]:
                key = k
                break
        else:
            return

        item = client.bot.convert_to_backend_type(key)
        asset = client.party.me.asset(item)
        variants = client.party.me.variants(item)
        enlightenment = client.party.me.enlightenments
        corruption = client.party.me.corruption
        styles = client.searcher.get_style(asset)

        async def add_style(style):
            attr = f'is_{client.bot.convert_backend_to_key(item)}_lock_for'
            if getattr(client, attr)(message.author.id):
                await message.reply(
                    client.l('cosmetic_locked')
                )
                return
            await client.party.me.change_asset(
                item,
                asset,
                variants=variants + style['variants'],
                enlightenment=enlightenment,
                corruption=corruption
            )

        if len(styles) == 0:
            await message.reply(
                client.l('no_style_change')
            )
        else:
            client.select[message.author.id] = {
                'exec': (
                    'await add_style(style)'
                ),
                'globals': {**globals(), **locals()},
                'variables': [
                    {'style': style}
                    for style in styles
                ]
            }
            await message.reply(
                ('\n'.join([f'{num}: {style["name"]}'
                            for num, style in enumerate(styles, 1)])
                    + '\n' + client.l('enter_number_to_select', client.bot.l('style')))
            )

    @command(
        name='set_variant',
        usage='{name} [{client.l("cosmetic_types", **self.variables_without_self)}] [variant] [{client.l("number")}]'
    )
    async def set_variant(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 4:
            await client.show_help(command, message)
            return

        if not any([message.args[1] in client.commands[key]
                    for key in ['outfit', 'backpack', 'pickaxe']]):
            await client.show_help(command, message)
            return

        for k in ['outfit', 'backpack', 'pickaxe']:
            if message.args[1] in client.commands[k]:
                key = k
                break
        else:
            return

        variant_dict = {}
        for num, text in enumerate(message.args[2:]):
            if num % 2 != 0:
                continue
            try:
                variant_dict[text] = message.args[num + 3]
            except IndexError:
                break
        item = client.bot.convert_to_backend_type(key)
        variants = client.party.me.create_variants(**variant_dict)
        asset = client.party.me.asset(item)
        enlightenment = client.party.me.enlightenments
        corruption = client.party.me.corruption

        attr = f'is_{client.bot.convert_backend_to_key(item)}_lock_for'
        if getattr(client, attr)(message.author.id):
            await message.reply(
                client.l('cosmetic_locked')
            )
            return
        await client.party.me.change_asset(
            item,
            asset,
            variants=variants,
            enlightenment=enlightenment,
            corruption=corruption
        )

    @command(
        name='add_variant',
        usage='{name} [{client.l("cosmetic_types", **self.variables_without_self)}] [variant] [{client.l("number")}]'
    )
    async def add_variant(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 4:
            await client.show_help(command, message)
            return

        if not any([message.args[1] in client.commands[key]
                    for key in ['outfit', 'backpack', 'pickaxe']]):
            await client.show_help(command, message)
            return

        for k in ['outfit', 'backpack', 'pickaxe']:
            if message.args[1] in client.commands[k]:
                key = k
                break
        else:
            return

        variant_dict = {}
        for num, text in enumerate(message.args[2:]):
            if num % 2 != 0:
                continue
            try:
                variant_dict[text] = message.args[num + 3]
            except IndexError:
                break
        item = client.bot.convert_to_backend_type(key)
        variants = client.party.me.variants(item)
        variants += client.party.me.create_variants(**variant_dict)
        asset = client.party.me.asset(item)
        enlightenment = client.party.me.enlightenments
        corruption = client.party.me.corruption

        attr = f'is_{client.bot.convert_backend_to_key(item)}_lock_for'
        if getattr(client, attr)(message.author.id):
            await message.reply(
                client.l('cosmetic_locked')
            )
            return
        await client.party.me.change_asset(
            item,
            asset,
            variants=variants,
            enlightenment=enlightenment,
            corruption=corruption
        )

    @command(
        name='cosmetic_preset',
        usage='{name} [{client.l("save_or_load", **self.variables_without_self)}] [{client.l("number")}]'
    )
    async def cosmetic_preset(command: Command, client: 'Client', message: MyMessage) -> None:
        if len(message.args) < 3:
            await client.show_help(command, message)
            return

        if not message.args[2].isdigit():
            await message.reply(
                client.l('please_enter_valid_number')
            )
            return

        number = message.args[2]
        if int(number) <= 0:
            await message.reply(
                client.l('please_enter_valid_number')
            )
            return

        if message.args[1] in client.commands['save']:
            if client.user.id not in client.bot.cosmetic_presets:
                client.bot.cosmetic_presets[client.user.id] = {}
            client.bot.cosmetic_presets[client.user.id][number] = {
                'AthenaCharacter': {
                    'asset': client.party.me.asset('AthenaCharacter'),
                    'variants': client.party.me.variants('AthenaCharacter')
                },
                'AthenaBackpack': {
                    'asset': client.party.me.asset('AthenaBackpack'),
                    'variants': client.party.me.variants('AthenaBackpack')
                },
                'AthenaPickaxe': {
                    'asset': client.party.me.asset('AthenaPickaxe'),
                    'variants': client.party.me.variants('AthenaPickaxe')
                },
                'AthenaDance': {
                    'asset': client.emote
                },
                'enlightenment': client.party.me.enlightenments,
                'corruption': client.party.me.corruption
            }
            client.bot.store_cosmetic_presets(client.user.id, client.bot.cosmetic_presets[client.user.id])
            await message.reply(
                client.l('cosmetic_preset_saved', number)
            )
        elif message.args[1] in client.commands['load']:
            if client.bot.cosmetic_presets.get(client.user.id, {}).get(number) is None:
                await message.reply(
                    client.l('cosmetic_preset_not_found')
                )
                return
            assets = client.bot.cosmetic_presets[client.user.id][number]
            coros = []

            items = [
                'AthenaCharacter',
                'AthenaBackpack',
                'AthenaPickaxe',
                'AthenaDance'
            ]
            for item in items:
                conf = client.bot.convert_backend_type(item)
                coro = client.party.me.change_asset(
                    item,
                    assets[item]['asset'],
                    variants=assets[item].get('variants'),
                    enlightenment=assets['enlightenment'],
                    corruption=assets['corruption'],
                    do_point=False
                )
                coro.__qualname__ = f'ClientPartyMember.set_{conf}'
                coros.append(coro)
            await client.party.me.edit(
                *coros
            )
            await message.reply(
                client.l('cosmetic_preset_loaded', number)
            )
        else:
            await message.reply(
                client.l('please_enter_valid_number')
            )

    @command(
        name='test',
        usage='{name}'
    )
    async def test(command: Command, client: 'Client', message: MyMessage) -> None:
        print('test command')
        await message.reply('Test dayo!')
