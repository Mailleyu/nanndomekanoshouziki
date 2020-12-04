# -*- coding: utf-8 -*-
import asyncio
import datetime
import io
import json
import logging
import os
import platform
import re
import sys
import textwrap
import traceback
from contextlib import redirect_stderr, redirect_stdout
from functools import partial
from glob import glob
from logging import WARNING, getLogger
from typing import Any, Callable, List, Optional, Tuple, Union

import aiohttp
import discord
import fortnitepy
import sanic
from pykakasi import kakasi

from .client import Client, MyClientParty, MyClientPartyMember
from .colors import cyan, green, red, yellow
from .commands import Command, DefaultCommands, MyMessage, PartyPrivacy
from .cosmetics import CaseInsensitiveDict, Searcher
from .device_code import Auth, HTTPClient
from .discord_client import DiscordClient
from .encoder import MyJSONEncoder
from .localize import LocalizedText
from .web import Web, WebMessage, WebUser
from .webhook import WebhookClient

if (os.getenv('REPLIT_DB_URL') is not None
        and os.getcwd().startswith('/home/runner')
        and sys.platform == 'linux'):
    from replit import db
else:
    db = None


Message = Union[
    fortnitepy.FriendMessage,
    fortnitepy.PartyMessage,
    discord.Message,
    WebMessage
]
Author = Union[
    fortnitepy.Friend,
    fortnitepy.PartyMember,
    discord.User,
    discord.Member,
    WebUser
]


class MyStream(io.StringIO):
    def __init__(self, original: io.IOBase, func: Optional[Callable] = None) -> None:
        self.original = original
        self.func = func if func is not None else (lambda x: x)
        super().__init__()

    def write(self, s: str) -> int:
        s = self.func(s)
        print(s, end='', file=self.original)
        return super().write(s)

    def read(self, size: Optional[int] = -1) -> str:
        self.seek(0)
        return super().read(size)


sys.stdout = MyStream(sys.stdout)
sys.stderr = MyStream(sys.stderr, red)


class Bot:
    BACKEND_TO_API_CONVERTER = {
        'AthenaBackpack': 'backpack',
        'AthenaPickaxe': 'pickaxe',
        'AthenaItemWrap': 'wrap',
        'AthenaGlider': 'glider',
        'AthenaCharacter': 'outfit',
        'AthenaPet': 'pet',
        'AthenaMusicPack': 'music',
        'AthenaLoadingScreen': 'loadingscreen',
        'AthenaDance': 'emote',
        'AthenaSpray': 'spray',
        'AthenaEmoji': 'emoji',
        'AthenaSkyDiveContrail': 'contrail',
        'AthenaPetCarrier': 'petcarrier',
        'AthenaToy': 'toy',
        'AthenaConsumableEmote': 'consumableemote',
        'AthenaBattleBus': 'battlebus',
        'AthenaVictoryPose': 'ridethepony',
        'BannerToken': 'banner'
    }
    API_TO_BACKEND_CONVERTER = {
        v: k for k, v in BACKEND_TO_API_CONVERTER.items()
    }
    BACKEND_TO_KEY_CONVERTER = {
        'AthenaBackpack': 'backpack',
        'AthenaPickaxe': 'pickaxe',
        'AthenaItemWrap': 'wrap',
        'AthenaGlider': 'glider',
        'AthenaCharacter': 'outfit',
        'AthenaPet': 'backpack',
        'AthenaMusicPack': 'music',
        'AthenaLoadingScreen': 'loadingscreen',
        'AthenaDance': 'emote',
        'AthenaSpray': 'emote',
        'AthenaEmoji': 'emote',
        'AthenaSkyDiveContrail': 'contrail',
        'AthenaPetCarrier': 'backpack',
        'AthenaToy': 'emote',
        'AthenaConsumableEmote': 'emote',
        'AthenaBattleBus': 'battlebus',
        'AthenaVictoryPose': 'emote',
        'BannerToken': 'banner'
    }
    BACKEND_TO_ID_CONVERTER = {
        'AthenaCharacter': 'CID',
        'AthenaBackpack': 'BID',
        'AthenaPetCarrier': 'PetCarrier',
        'AthenaPet': 'PetID',
        'AthenaPickaxe': 'Pickaxe_ID',
        'AthenaDance': 'EID',
        'AthenaEmoji': 'Emoji',
        'AthenaToy': 'Toy',
        'AthenaConsumableEmote': 'EID',
    }

    def __init__(self, mode: str, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

        self.mode = mode

        self.clients = []
        self.web = Web(self, __name__)
        self.web_text = ''
        self.server = None
        self.lang_dir = 'lang'
        self.item_dir = 'item'
        os.makedirs(self.item_dir, exist_ok=True)

        self.booted_at = None
        self.email_pattern = re.compile(
            r'[a-zA-Z0-9.+-]+@[a-zA-Z0-9]+\.[a-zA-Z0-9]+'
        )
        self.format_pattern = re.compile(r'\{(.*?)\}')
        self.return_pattern = re.compile(
            r'(?P<space>\s*)(return|return\s+(?P<text>.*))\s*'
        )
        self.kakasi = kakasi()
        self.kakasi.setMode('J', 'H')
        self.localize = None

        self.all_commands = {
            attr.name: attr
            for attr in DefaultCommands.__dict__.values()
            if isinstance(attr, Command)
        }
        print(len(self.all_commands), self.all_commands.keys())

        self.none_data = {
            'real_value': None,
            'value': 'None',
            'display_value': self.l('none_none', default='null')
        }
        self.select_bool = [
            {
                'real_value': True,
                'value': 'True',
                'display_value': self.l('bool_true', default='true')
            },
            {
                'real_value': False,
                'value': 'False',
                'display_value': self.l('bool_false', default='false')
            }
        ]
        self.select_event = [
            {
                'real_value': i,
                'value': i,
                'display_value': self.l(f'event_{i}', default=i)
            } for i in ['me', 'user']
        ]
        self.select_platform = [
            {
                'real_value': i,
                'value': i,
                'display_value': self.l(f'platform_{i}', default=i)
            } for i in ['WIN', 'MAC', 'PS4', 'PS5', 'XBL',
                        'XBX', 'XBS', 'SWT', 'IOS', 'AND']
        ]
        self.select_privacy = [
            {
                'real_value': i,
                'value': i,
                'display_value': self.l(f'privacy_{i.lower()}', default=i.upper())
            } for i in ['PUBLIC', 'FRIENDS_ALLOW_FRIENDS_OF_FRIENDS',
                        'FRIENDS', 'PRIVATE_ALLOW_FRIENDS_OF_FRIENDS',
                        'PRIVATE']
        ]
        self.select_status = [
            {
                'real_value': i,
                'value': i,
                'display_value': self.l(f'status_type_{i}', default=i)
            } for i in ['playing', 'streaming', 'listening', 'watching', 'competing']
        ]
        self.select_matchmethod = [
            {
                'real_value': i,
                'value': i,
                'display_value': self.l(f'matchmethod_{i}', default=i)
            } for i in ['full', 'contains', 'starts', 'ends']
        ]
        self.select_lang = [
            {
                'real_value': re.sub(r'lang(\\|/)', '', i).replace('.json', ''),
                'value': re.sub(r'lang(\\|/)', '', i).replace('.json', ''),
                'display_value': re.sub(r'lang(\\|/)', '', i).replace('.json', '')
            } for i in glob('lang/*.json') if not i.endswith('_old.json')
        ]
        self.select_api_lang = [
            {
                'real_value': i,
                'value': i,
                'display_value': i
            } for i in ['ar', 'de', 'en', 'es', 'es-419', 'fr', 'it', 'ja',
                        'ko', 'pl', 'pt-BR', 'ru', 'tr', 'zh-CN', 'zh-Hant']
        ]
        self.select_api = [
            {
                'real_value': i,
                'value': i,
                'display_value': i
            } for i in ['BenBot', 'Fortnite-API', 'FortniteApi.io']
        ]
        self.select_loglevel = [
            {
                'real_value': i,
                'value': i,
                'display_value': self.l(f'loglevel_{i}', default=i)
            } for i in ['normal', 'info', 'debug']
        ]

        self.multiple_select_user_type = [
            {
                'real_value': i,
                'value': i,
                'display_value': self.l(f'multiple_select_{i} ', default=i)
            } for i in ['user', 'whitelist', 'blacklist', 'owner', 'bot']
        ]
        self.multiple_select_user_operation = [
            {
                'real_value': i,
                'value': i,
                'display_value': self.l(f'multiple_select_{i}', default=i)
            } for i in ['kick', 'chatban', 'remove', 'block', 'blacklist']
        ]
        self.multiple_select_platform = self.select_platform

        self.config = None
        self.config_tags = {
            "['clients']": [list, dict, 'can_extend', 'client_config', 'lambda x: len(x) > 0'],
            "['discord']": [dict],
            "['discord']['enabled']": [bool, 'select_bool'],
            "['discord']['token']": [str],
            "['discord']['owner']": [list, int, 'can_be_none'],
            "['discord']['channels']": [list, str],
            "['discord']['status']": [str],
            "['discord']['status_type']": [str, 'select_status'],
            "['discord']['command_enable_for']": [list, str, 'multiple_select_user_type'],
            "['discord']['blacklist']": [list, int],
            "['discord']['whitelist']": [list, int],
            "['web']": [dict],
            "['web']['enabled']": [bool, 'select_bool'],
            "['web']['ip']": [str],
            "['web']['port']": [int],
            "['web']['password']": [str],
            "['web']['login_required']": [bool, 'select_bool'],
            "['web']['command_web']": [bool, 'select_bool'],
            "['web']['access_log']": [bool, 'select_bool'],
            "['lang']": [str, 'select_lang'],
            "['search_lang']": [str, 'select_api_lang'],
            "['sub_search_lang']": [str, 'select_api_lang'],
            "['api']": [str, 'select_api'],
            "['api_key']": [str, 'can_be_none'],
            "['discord_log']": [str, 'can_be_none'],
            "['hide_email']": [bool, 'select_bool'],
            "['hide_password']": [bool, 'select_bool'],
            "['hide_token']": [bool, 'select_bool'],
            "['hide_webhook']": [bool, 'select_bool'],
            "['no_logs']": [bool, 'select_bool'],
            "['loglevel']": [str, 'select_loglevel'],
            "['debug']": [bool, 'select_bool']
        }
        self.client_config_tags = {
            "['fortnite']": [dict],
            "['fortnite']['email']": [str, 'lambda x: self.email_pattern.match(x) is not None'],
            "['fortnite']['owner']": [list, str, 'can_be_none'],
            "['fortnite']['outfit']": [str, 'can_be_none'],
            "['fortnite']['outfit_style']": [list, str, 'can_be_none'],
            "['fortnite']['ng_outfits']": [list, str, 'can_be_none'],
            "['fortnite']['ng_outfit_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['ng_outfit_operation']": [list, str, 'multiple_select_user_operation', 'can_be_none'],
            "['fortnite']['join_outfit']": [str, 'can_be_none'],
            "['fortnite']['join_outfit_style']": [list, str, 'can_be_none'],
            "['fortnite']['join_outfit_on']": [str, 'select_event'],
            "['fortnite']['leave_outfit']": [str, 'can_be_none'],
            "['fortnite']['leave_outfit_style']": [list, str, 'can_be_none'],
            "['fortnite']['leave_outfit_on']": [str, 'select_event'],
            "['fortnite']['outfit_mimic_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['outfit_lock_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['backpack']": [str, 'can_be_none'],
            "['fortnite']['backpack_style']": [list, str, 'can_be_none'],
            "['fortnite']['ng_backpacks']": [list, str, 'can_be_none'],
            "['fortnite']['ng_backpack_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['ng_backpack_operation']": [list, str, 'multiple_select_user_operation', 'can_be_none'],
            "['fortnite']['join_backpack']": [str, 'can_be_none'],
            "['fortnite']['join_backpack_style']": [list, str, 'can_be_none'],
            "['fortnite']['join_backpack_on']": [str, 'select_event'],
            "['fortnite']['leave_backpack']": [str, 'can_be_none'],
            "['fortnite']['leave_backpack_style']": [list, str, 'can_be_none'],
            "['fortnite']['leave_backpack_on']": [str, 'select_event'],
            "['fortnite']['backpack_mimic_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['backpack_lock_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['pickaxe']": [str, 'can_be_none'],
            "['fortnite']['pickaxe_style']": [list, str, 'can_be_none'],
            "['fortnite']['ng_pickaxes']": [list, str, 'can_be_none'],
            "['fortnite']['ng_pickaxe_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['ng_pickaxe_operation']": [list, str, 'multiple_select_user_operation', 'can_be_none'],
            "['fortnite']['join_pickaxe']": [str, 'can_be_none'],
            "['fortnite']['join_pickaxe_style']": [list, str, 'can_be_none'],
            "['fortnite']['join_pickaxe_on']": [str, 'select_event'],
            "['fortnite']['leave_pickaxe']": [str, 'can_be_none'],
            "['fortnite']['leave_pickaxe_style']": [list, str, 'can_be_none'],
            "['fortnite']['leave_pickaxe_on']": [str, 'select_event'],
            "['fortnite']['pickaxe_mimic_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['pickaxe_lock_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['emote']": [str],
            "['fortnite']['emote_section']": [int, 'can_be_none'],
            "['fortnite']['repeat_emote_when_join']": [bool, 'select_bool'],
            "['fortnite']['ng_emotes']": [list, str, 'can_be_none'],
            "['fortnite']['ng_emote_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['ng_emote_operation']": [list, str, 'multiple_select_user_operation', 'can_be_none'],
            "['fortnite']['join_emote']": [str, 'can_be_none'],
            "['fortnite']['join_emote_section']": [int, 'can_be_none'],
            "['fortnite']['join_emote_on']": [str, 'select_event'],
            "['fortnite']['leave_emote']": [str, 'can_be_none'],
            "['fortnite']['leave_emote_section']": [int, 'can_be_none'],
            "['fortnite']['leave_emote_on']": [str, 'select_event'],
            "['fortnite']['emote_mimic_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['emote_lock_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['leave_delay_for']": [float],
            "['fortnite']['refresh_on_reload']": [bool, 'select_bool'],
            "['fortnite']['party']": [dict],
            "['fortnite']['party']['privacy']": [str, 'select_privacy'],
            "['fortnite']['party']['max_size']": [int, 'lambda x: 1 <= x <= 16'],
            "['fortnite']['party']['allow_swap']": [bool, 'select_bool'],
            "['fortnite']['party']['playlist']": [str],
            "['fortnite']['party']['disable_voice_chat']": [bool, 'select_bool'],
            "['fortnite']['avatar_id']": [str, 'can_be_none'],
            "['fortnite']['avatar_color']": [str, 'can_be_multiple', 'can_be_none', 'lambda x: x != "" and (len(x.split(",")) >= 3) if "," in x else (getattr(fortnitepy.KairosBackgroundColorPreset, x.upper(), None) is not None)'],  # noqa
            "['fortnite']['banner_id']": [str],
            "['fortnite']['banner_color']": [str],
            "['fortnite']['level']": [int],
            "['fortnite']['tier']": [int],
            "['fortnite']['xp_boost']": [int],
            "['fortnite']['friend_xp_boost']": [int],
            "['fortnite']['platform']": [str, 'select_platform'],
            "['fortnite']['ng_platforms']": [list, str, 'multiple_select_platform', 'can_be_none'],
            "['fortnite']['ng_platform_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['ng_platform_operation']": [list, str, 'multiple_select_user_operation', 'can_be_none'],
            "['fortnite']['status']": [str],
            "['fortnite']['accept_invite_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['decline_invite_when']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['invite_interval']": [float, 'can_be_none'],
            "['fortnite']['accept_friend_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['send_friend_request']": [bool, 'select_bool'],
            "['fortnite']['whisper_enable_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['party_chat_enable_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['accept_join_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['join_message']": [list, str, 'can_be_none'],
            "['fortnite']['join_message_whisper']": [list, str, 'can_be_none'],
            "['fortnite']['random_message']": [list, list, str, 'can_be_none'],
            "['fortnite']['random_message_whisper']": [list, list, str, 'can_be_none'],
            "['fortnite']['chat_max']": [int],
            "['fortnite']['kick_disconnect']": [bool, 'select_bool'],
            "['fortnite']['kick_in_match']": [bool, 'select_bool'],
            "['fortnite']['hide_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['fortnite']['blacklist']": [list, str],
            "['fortnite']['blacklist_operation']": [list, str, 'multiple_select_user_operation', 'can_be_none'],
            "['fortnite']['blacklist_decline_join']": [bool, 'select_bool'],
            "['fortnite']['whitelist']": [list, str],
            "['fortnite']['invitelist']": [list, str],
            "['fortnite']['botlist']": [list, str],
            "['fortnite']['botlist_operation']": [list, str, 'multiple_select_user_operation', 'can_be_none'],
            "['fortnite']['exec']": [dict],
            "['fortnite']['exec']['ready']": [list, str, 'can_be_none'],
            "['discord']['enabled']": [bool, 'select_bool'],
            "['discord']['token']": [str],
            "['discord']['owner']": [list, int, 'can_be_none'],
            "['discord']['channels']": [list, str],
            "['discord']['status']": [str],
            "['discord']['status_type']": [str, 'select_status'],
            "['discord']['command_enable_for']": [list, str, 'multiple_select_user_type'],
            "['discord']['blacklist']": [list, int],
            "['discord']['whitelist']": [list, int],
            "['ng_words']": [list, str, 'can_extend', 'ng_words_config'],
            "['ng_word_for']": [list, str, 'multiple_select_user_type', 'can_be_none'],
            "['ng_word_operation']": [list, str, 'multiple_select_user_operation', 'can_be_none'],
            "['restart_in']": [int, 'can_be_none'],
            "['lang']": [str, 'select_lang'],
            "['search_max']": [int, 'can_be_none'],
            "['no_logs']": [bool, 'select_bool'],
            "['discord_log']": [str, 'can_be_none'],
            "['omit_over2000']": [bool, 'select_bool'],
            "['skip_if_overflow']": [bool, 'select_bool'],
            "['case_insensitive']": [bool, 'select_bool'],
            "['convert_kanji']": [bool, 'select_bool']
        }
        self.ng_words_config_tags = {
            "['count']": [int],
            "['matchmethod']": [str, 'select_matchmethod'],
            "['word']": [list, str]
        }

        self.commands = None
        tags = [list, str, 'can_be_multiple']
        self.commands_tags = {
            **{
                "['whitelist_commands']": tags,
                "['user_commands']": tags,
                "['true']": tags,
                "['false']": tags,
                "['accept']": tags,
                "['decline']": tags,
                "['me']": tags,
                "['public']": tags,
                "['friends_allow_friends_of_friends']": tags,
                "['friends']": tags,
                "['private_allow_friends_of_friends']": tags,
                "['private']": tags,
                "['commands']": [dict]
            },
            **{
                f"['commands']['{command}']": tags
                for command in self.all_commands.keys()
            }
        }

        self.cosmetic_presets = None

        self.config_item_pattern = re.compile(
            r"<Item name='(?P<name>.+)' "
            r"id='(?P<id>.+)'>"
        )
        self.config_playlist_pattern = re.compile(
            r"<Playlist name='(?P<name>.+)' "
            r"id='(?P<id>.+)'>"
        )
        self.config_variant_pattern = re.compile(
            r"<Variant name='(?P<name>.+)' "
            r"channel='(?P<channel>.+)' "
            r"tag='(?P<tag>.+)'>"
        )

        self.session = aiohttp.ClientSession()
        self.http = HTTPClient(self.session, self.loop)
        self.auth = Auth(self, self.http)
        self.webhook = None
        self.discord_client = None

    @property
    def loaded_clients(self) -> List[Client]:
        return [client for client in self.clients if client.is_ready()]

    @property
    def loaded_client_ids(self) -> List[Client]:
        return [client.user.id for client in self.loaded_clients]

    def add_command(self, command: Command) -> None:
        if not isinstance(command, Command):
            raise TypeError(f'command argument must be instance of {Command.__name__}')
        if command.name in self.all_commands:
            raise ValueError(f"Command '{command.name}' is already registered")

        self.all_commands[command.name] = command
        for client in self.clients:
            client.add_command(command)

    def is_error(self) -> None:
        return self.error_config or self.error_commands

    def get_device_auth_details(self) -> None:
        if self.isfile('device_auths'):
            return self.load_json('device_auths')
        else:
            return {}

    def store_device_auth_details(self, email: str, details: dict) -> None:
        existing = self.get_device_auth_details()
        existing[email.lower()] = details
        self.save_json('device_auths', existing)

    def get_cosmetic_presets(self) -> None:
        if self.isfile('cosmetic_presets'):
            return self.load_json('cosmetic_presets')
        else:
            return {}

    def store_cosmetic_presets(self, account_id: str, details: dict) -> None:
        existing = self.get_cosmetic_presets()
        existing[account_id] = details
        self.save_json('cosmetic_presets', existing)

    def convert_td(self, td: datetime.timedelta) -> Tuple[int, int, int, int]:
        m, s = divmod(td.seconds, 60)
        h, m = divmod(m, 60)
        d, h = divmod(h, 24)
        return d, h, m, s

    def isfile(self, key: str, force_file: Optional[bool] = False) -> bool:
        if self.mode == 'repl' and not force_file:
            if db.get(key) is None:
                return False
        else:
            if not os.path.isfile(f'{key}.json'):
                return False
        return True

    def remove(self, key: str, force_file: Optional[bool] = False) -> None:
        if self.mode == 'repl' and not force_file:
            try:
                del db[key]
            except KeyError as e:
                raise FileNotFoundError from e
        else:
            os.remove(f'{key}.json')

    def rename(self, key_src: str, key_dst: str, force_file: Optional[bool] = False) -> None:
        if self.mode == 'repl' and not force_file:
            try:
                db[key_dst] = db[key_src]
                del db[key_src]
            except KeyError as e:
                raise FileNotFoundError from e
        else:
            os.rename(f'{key_src}.json', f'{key_dst}.json')

    def load_json(self, key: str, force_file: Optional[bool] = False) -> Union[dict, list]:
        if self.mode == 'repl' and not force_file:
            return db[key]['value']
        else:
            try:
                with open(f'{key}.json', encoding='utf-8') as f:
                    data = f.read()
            except UnicodeDecodeError:
                try:
                    with open(f'{key}.json', encoding='utf-8-sig') as f:
                        data = f.read()
                except UnicodeDecodeError:
                    with open(f'{key}.json', encoding='shift_jis') as f:
                        data = f.read()
            return json.loads(data)

    def save_json(self, key: str, value: Union[dict, list],
                  force_file: Optional[bool] = False,
                  compact: Optional[bool] = False) -> None:
        if self.mode == 'repl' and not force_file:
            db[key] = {
                'last_edited': self.utcnow(),
                'value': self.json_serializer(value)
            }
        else:
            with open(f'{key}.json', 'w', encoding='utf-8') as f:
                if compact:
                    json.dump(
                        value,
                        f,
                        ensure_ascii=False,
                        cls=MyJSONEncoder
                    )
                else:
                    json.dump(
                        value,
                        f,
                        indent=4,
                        ensure_ascii=False,
                        cls=MyJSONEncoder
                    )

    def get_last_edited(self, key: str, force_file: Optional[bool] = False) -> datetime.datetime:
        if self.mode == 'repl' and not force_file:
            return datetime.datetime.fromisoformat(db[key]['last_edited'])
        else:
            stat = os.stat(f'{key}.json')
            return datetime.datetime.fromtimestamp(stat.st_mtime)

    def is_not_edited_for(self, key: str, td: datetime.timedelta, force_file: Optional[bool] = False) -> bool:
        last_edited = self.get_last_edited(key)
        if last_edited < (datetime.datetime.utcnow() - td):
            return True
        return False

    def l(self, key: str, *args: tuple, default: Optional[str] = '', **kwargs: dict) -> LocalizedText:
        return LocalizedText(self, ['main', key], default, *args, **kwargs)

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
            add_d.append(self.discord_error)
        if not self.config['no_logs'] if self.config else True:
            text = content
            for func in add_p:
                text = func(text)
            print(color(text), file=file)

        if self.webhook:
            content = discord.utils.escape_markdown(content)
            name = user_name or 'Fortnite-LobbyBot'
            text = content
            for func in add_d:
                text = func(text)
            self.webhook.send(text, name)

    def time(self, text: str) -> str:
        return f'[{self.now()}] {text}'

    def discord_error(self, text: str) -> str:
        texts = []
        for line in text.split('\n'):
            texts.append(f'> {line}')
        return '\n'.join(texts)

    def debug_message(self, text: str) -> str:
        return f'```\n{text}\n```'

    def format_exception(self, exc: Optional[Exception] = None) -> str:
        if exc is not None:
            return ''.join(list(traceback.TracebackException.from_exception(exc).format()))
        return traceback.format_exc()

    def print_exception(self, exc: Optional[Exception] = None) -> None:
        if exc is not None:
            self.send(
                ''.join(['Ignoring exception\n']
                        + list(traceback.TracebackException.from_exception(exc).format())),
                file=sys.stderr
            )
        else:
            self.send(
                traceback.format_exc(),
                file=sys.stderr
            )

    def debug_print_exception(self, exc: Optional[Exception] = None) -> None:
        if self.config is not None and self.config['loglevel'] == 'debug':
            self.print_exception(exc)

    def now(self) -> str:
        return datetime.datetime.now().strftime('%H:%M:%S')

    def utcnow(self) -> str:
        return datetime.datetime.utcnow().strftime('%H:%M:%S')

    def get_list_index(self, data: list, index: int, default: Optional[Any] = None) -> Any:
        return data[index] if data[index:index + 1] else default

    def eval_format(self, text: str, variables: dict) -> str:
        for match in self.format_pattern.finditer(text):
            match_text = match.group()
            try:
                text = text.replace(match_text, match_text.format_map(variables), 1)
            except Exception as e:
                self.debug_print_exception(e)
                result = eval(match_text[1:-1], globals(), variables)
                text = text.replace(match_text, str(result), 1)
        return text

    def eval_dict(self, data: dict, keys: list) -> str:
        text = ''
        for key in keys:
            if isinstance(key, str):
                text += f"['{key}']"
            else:
                text += f"[{key}]"
        return text

    def get_dict_key(self, data: dict, keys: list,
                     func: Optional[Callable] = None) -> Any:
        func = func or (lambda x: x)
        text = self.eval_dict(data, keys)
        return func(eval(f'data{text}'))

    def set_dict_key(self, data: dict, keys: list, value: Any,
                     func: Optional[Callable] = None) -> None:
        func = func or (lambda x: x)
        text = self.eval_dict(data, keys)
        exec(f'data{text} = func(value)')

    def eval_dict_default(self, data: dict, keys: list) -> Tuple[str, str]:
        text = ''
        text2 = ''
        for nest, key in enumerate(keys, 1):
            if isinstance(key, str):
                text += f"['{key}']"
            else:
                text += f"[{key}]"
            if nest == len(keys):
                if isinstance(key, str):
                    text2 += f".get('''{key}''', default)"
                else:
                    text2 = f"self.get_list_index(data{text2}, key, default)"
            else:
                text2 += f"['''{key}''']"
        return text, text2

    def get_dict_key_default(self, data: dict, keys: list, default: Any,
                             func: Optional[Callable] = None) -> Any:
        func = func or (lambda x: x)
        _, text2 = self.eval_dict_default(data, keys)
        try:
            value = eval(f'data{text2}')
        except TypeError:
            value = default
        return func(value)

    def set_dict_key_default(self, data: dict, keys: list, default: Any,
                             func: Optional[Callable] = None) -> None:
        func = func or (lambda x: x)
        text, text2 = self.eval_dict_default(data, keys)
        try:
            value = eval(f'data{text2}')  # noqa
        except ValueError:
            value = default  # noqa
        exec(f'data{text} = func(value)')

    def load_config(self) -> Optional[Tuple[dict, list]]:
        try:
            config = self.load_json('config')
        except (json.decoder.JSONDecodeError, UnicodeDecodeError) as e:
            self.send(
                (f'{self.format_exception(e)}\n{e}\n'
                 + self.l(
                     'load_failed_json',
                     'config',
                     default=(
                         "'{0}' ファイルの読み込みに失敗しました。正しく書き込めているか確認してください\n"
                         "Failed to load '{0}' file. Make sure you wrote correctly"
                     )
                 )),
                file=sys.stderr
            )
            return None, None
        except FileNotFoundError as e:
            self.send(
                (f'{self.format_exception(e)}\n{e}\n'
                 + self.l(
                     'load_failed_not_found',
                     'config',
                     default=(
                         "'{0}' ファイルが存在しません\n"
                         "'{0}' file does not exist"
                     )
                 )),
                file=sys.stderr
            )
            return None, None
        self.set_dict_key_default(config, ['clients'], [])
        self.set_dict_key_default(config, ['web'], {})
        self.set_dict_key_default(config, ['web', 'enabled'], True)
        self.set_dict_key_default(config, ['web', 'ip'], '{ip}')
        self.set_dict_key_default(config, ['web', 'port'], 8000)
        self.set_dict_key_default(config, ['lang'], 'en')
        self.set_dict_key_default(config, ['api'], 'BenBot')
        self.set_dict_key_default(config, ['api_key'], None)
        self.set_dict_key_default(config, ['discord_log'], None)
        self.set_dict_key_default(config, ['loglevel'], 'normal')
        self.set_dict_key_default(config, ['debug'], False)

        if self.mode in ['repl', 'glitch']:
            replace = '0.0.0.0'
        else:
            replace = 'localhost'
        config['web']['ip'] = config['web']['ip'].format(ip=replace)

        error_config = []
        for key, tags in self.config_tags.items():
            try:
                value = eval(f'config{key}')
            except KeyError:
                self.send(
                    self.l(
                        'is_missing',
                        key,
                        default=(
                            "{0} がありません\n"
                            "{0} is missing"
                        )
                    ),
                    file=sys.stderr
                )
                error_config.append(key)
            else:
                self.tag_check(config, error_config, key, tags, value)
        if config['loglevel'] == 'debug':
            self.send(json.dumps(config, indent=4, ensure_ascii=False),
                      color=yellow, add_d=lambda x: f'{self.debug_message(x)}\n')
        self.save_json('config', config)
        if config['api'] == 'FortniteApi.io' and not config['api_key']:
            self.send(
                self.l('api_key_required'),
                add_p=self.time,
                file=sys.stderr
            )
            error_config.append("['api_key']")

        return config, error_config

    def load_localize(self, lang: str) -> Optional[dict]:
        try:
            localize = self.load_json(f'{self.lang_dir}/{lang}')
        except (json.decoder.JSONDecodeError, UnicodeDecodeError) as e:
            self.send(
                (f'{self.format_exception(e)}\n{e}\n'
                 + self.l(
                     'load_failed_json',
                     f'{self.lang_dir}/{lang}',
                     default=(
                         "'{0}' ファイルの読み込みに失敗しました。正しく書き込めているか確認してください\n"
                         "Failed to load '{0}' file. Make sure you wrote correctly"
                     )
                 )),
                file=sys.stderr
            )
            return None
        except FileNotFoundError as e:
            self.send(
                (f'{self.format_exception(e)}\n{e}\n'
                 + self.l(
                     'load_failed_not_found',
                     f'{self.lang_dir}/{lang}',
                     default=(
                         "'{0}' ファイルが存在しません\n"
                         "'{0}' file does not exist"
                     )
                 )),
                file=sys.stderr
            )
            return None
        return localize

    def load_commands(self) -> Optional[Tuple[dict, list]]:
        try:
            commands = self.load_json('commands')
        except (json.decoder.JSONDecodeError, UnicodeDecodeError) as e:
            self.send(
                (f'{self.format_exception(e)}\n{e}\n'
                 + self.l(
                     'load_failed_json',
                     'commands',
                     default=(
                         "'{0}' ファイルの読み込みに失敗しました。正しく書き込めているか確認してください\n"
                         "Failed to load '{0}' file. Make sure you wrote correctly"
                     )
                 )),
                file=sys.stderr
            )
            return None, None
        except FileNotFoundError as e:
            self.send(
                (f'{self.format_exception(e)}\n{e}\n'
                 + self.l(
                     'load_failed_not_found',
                     'commands',
                     default=(
                         "'{0}' ファイルが存在しません\n"
                         "'{0}' file does not exist"
                     )
                 )),
                file=sys.stderr
            )
            return None, None

        error_commands = []
        for key, tags in self.commands_tags.items():
            try:
                value = eval(f'commands{key}')
            except KeyError:
                self.send(
                    self.l(
                        'is_missing',
                        key,
                        default=(
                            "{0} がありません\n"
                            "{0} is missing\n"
                        )
                    ),
                    file=sys.stderr
                )
                error_commands.append(key)
            else:
                self.tag_check(commands, error_commands, key, tags, value)
        if self.config['loglevel'] == 'debug':
            self.send(json.dumps(commands, indent=4, ensure_ascii=False),
                      color=yellow, add_d=lambda x: f'{self.debug_message(x)}\n')
        self.save_json('commands', commands)

        return commands, error_commands

    def tag_check(self, data: dict, error_list: list,
                  key: str, tags: list, value: Any) -> None:
        select_tag = [tag for tag in tags if (isinstance(tag, str)
                                              and tag.startswith('select_'))]
        multiple_select_tag = [tag for tag in tags if (isinstance(tag, str)
                                                       and tag.startswith('multiple_select_'))]
        ok_tags = (tags[0],)
        if tags[0] is float:
            ok_tags = (*ok_tags, int)
        if 'can_be_none' in tags:
            ok_tags = (*ok_tags, None.__class__)
            for tag in select_tag:
                _tag = getattr(self, tag)
                if self.none_data not in _tag:
                    _tag.append(self.none_data)
            for tag in multiple_select_tag:
                _tag = getattr(self, tag)
                if self.none_data not in _tag:
                    _tag.append(self.none_data)
        if 'client_config' in tags:
            self.tag_check_client_config(data, error_list, key, value)
        elif not isinstance(value, ok_tags):
            if 'can_be_none' not in tags:
                expected = f'{tags[0].__name__}'
            else:
                expected = f'{tags[0].__name__}, {None.__class__.__name__}'
            provided = type(value).__name__

            failed = False
            if tags[0] in [bool, str, int]:
                try:
                    exec(f'data{key} = tags[0](value)')
                    value = eval(f'data{key}')
                except Exception as e:
                    self.debug_print_exception(e)
                    failed = True
            elif tags[0] is list:
                if tags[1] is list:
                    if isinstance(value, str):
                        try:
                            exec(f'data{key} = json.loads(value)')
                            value = eval(f'data{key}')
                        except Exception as e:
                            self.debug_print_exception(e)
                            failed = True
                    else:
                        failed = True
                elif tags[1] is str:
                    if isinstance(value, str):
                        try:
                            if value != '':
                                exec(f'data{key} = value.split(",")')
                                value = eval(f'data{key}')
                            else:
                                exec(f'data{key} = []')
                                value = eval(f'data{key}')
                        except Exception as e:
                            self.debug_print_exception(e)
                            try:
                                exec(f'data{key} = [value]')
                                value = eval(f'data{key}')
                            except Exception as e:
                                self.debug_print_exception(e)
                                failed = True
                    else:
                        failed = True
                elif tags[1] is int:
                    if isinstance(value, int):
                        try:
                            exec(f'data{key} = [value]')
                            value = eval(f'data{key}')
                        except Exception as e:
                            self.debug_print_exception(e)
                            failed = True
                    else:
                        try:
                            exec(f'data{key} = [int(value)]')
                            value = eval(f'data{key}')
                        except Exception as e:
                            self.debug_print_exception(e)
                            failed = True
            if failed:
                self.send(
                    self.l(
                        'type_mismatch',
                        key,
                        expected,
                        provided,
                        default=(
                            "'{0}' 型が一致しません(予想: '{1}' 実際: '{2}')\n"
                            "'{0}' type mismatch(Expected: '{1}' Provided: '{2}')\n"
                        )
                    ),
                    file=sys.stderr
                )
                error_list.append(key)
            else:
                self.send(
                    self.l(
                        'type_mismatch_fixed',
                        key,
                        expected,
                        provided,
                        eval(f'data{key}'),
                        default=(
                            "'{0}' 型が一致しません(予想: '{1}' 実際: '{2}') -> 修正されました: '{3}'\n"
                            "'{0}' type mismatch(Expected: '{1}' Provided: '{2}') -> Fixed: '{3}'\n"
                        )
                    ),
                    color=yellow,
                    add_d=self.discord_error
                )

        if key not in error_list:
            if tags[0] is list and value is not None:
                try:
                    exec(f'data{key} = self.cleanup_list(value)')
                except Exception as e:
                    self.debug_print_exception(e)
                else:
                    if 'client_config' not in tags:
                        for num, val in enumerate(value):
                            self.tag_check(data, error_list, f'{key}[{num}]', tags[1:], val)

            if len(select_tag) > 0:
                for tag in select_tag:
                    values = [
                        i['real_value'].lower() if isinstance(i['real_value'], str) else i['real_value']
                        for i in getattr(self, tag)
                    ]
                    if (value.lower() if isinstance(value, str) else value) not in values:
                        self.send(
                            self.l(
                                'not_in_select',
                                key,
                                value,
                                values,
                                default=(
                                    "'{0}' '{1}' は {2} のどれにも一致しません\n"
                                    "'{0}' '{1}' don't match to any of {2}\n"
                                )
                            ),
                            file=sys.stderr
                        )
                        error_list.append(key)
                    else:
                        v = CaseInsensitiveDict({i['real_value']: i for i in getattr(self, tag)})
                        exec(f'data{key} = v[value]["real_value"]')
            elif len(multiple_select_tag) > 0:
                for tag in multiple_select_tag:
                    values = [
                        i['real_value'].lower() if isinstance(i['real_value'], str) else i['real_value']
                        for i in getattr(self, tag)
                    ]
                    vals = []
                    if value is None:
                        vals = [None]
                    else:
                        if tags[0] is list:
                            vals = value
                        elif tags[0] is str:
                            vals = value.split(',')
                    for num, val in enumerate(vals):
                        if (val.lower() if isinstance(val, str) else val) not in values:
                            self.send(
                                self.l(
                                    'not_in_select',
                                    key,
                                    value,
                                    values,
                                    default=(
                                        "'{0}' '{1}' は {2} のどれにも一致しません\n"
                                        "'{0}' '{1}' don't match to any of {2}\n"
                                    )
                                ),
                                file=sys.stderr
                            )
                            error_list.append(key)
                            break
                        else:
                            if value is not None:
                                v = CaseInsensitiveDict({i['real_value']: i for i in getattr(self, tag)})
                                if tags[0] is list:
                                    vals[num] = v[val]['real_value']
                                    exec(f'data{key} = vals')
                                elif tags[0] is str:
                                    vals[num] = v[val]['real_value']
                                    exec(f'data{key} = ",".join(vals)')

            func_str = tags[-1]
            if not isinstance(func_str, str) or not func_str.startswith('lambda '):
                return
            try:
                func = eval(func_str, {**globals(), **locals()})
            except Exception:
                pass
            else:
                if not func(value):
                    self.send(
                        self.l(
                            'check_failed',
                            key,
                            value,
                            func_str,
                            default=(
                                "{0} '{1}' はチェック '{2}' に一致しません\n"
                                "{0} '{1}' don't match to check '{2}'\n"
                            )
                        ),
                        file=sys.stderr
                    )
                    error_list.append(key)

    def tag_check_client_config(self, data: dict, error_list: list,
                                key: str, value: Any) -> None:
        for count in range(len(value)):
            for c_key, c_tags in self.client_config_tags.items():
                try:
                    c_value = eval(f'value[{count}]{c_key}')
                except KeyError:
                    self.send(
                        self.l(
                            'is_missing',
                            f'{key}[{count}]{c_key}',
                            default=(
                                "{0} がありません\n"
                                "{0} is missing\n"
                            )
                        ),
                        file=sys.stderr
                    )
                    error_list.append(f'{key}[{count}]{c_key}')
                else:
                    if 'ng_words_config' in c_tags:
                        self.tag_check_ng_words_config(data, error_list, f'{key}[{count}]{c_key}', c_value)
                    else:
                        self.tag_check(data, error_list, f'{key}[{count}]{c_key}', c_tags, c_value)

    def tag_check_ng_words_config(self, data: dict, error_list: list,
                                  key: str, value: Any) -> None:
        for count in range(len(value)):
            for n_key, n_tags in self.ng_words_config_tags.items():
                try:
                    n_value = eval(f'value[{count}]{n_key}')
                except KeyError:
                    self.send(
                        self.l(
                            'is_missing',
                            f'{key}[{count}]{n_key}',
                            default=(
                                "{0} がありません\n"
                                "{0} is missing\n"
                            )
                        ),
                        file=sys.stderr
                    )
                    error_list.append(f'{key}[{count}]{n_key}')
                else:
                    self.tag_check(data, error_list, f'{key}[{count}]{n_key}', n_tags, n_value)

    def cleanup_email(self, email: str) -> str:
        return re.sub(r'\.|\+', '', email).lower()

    def cleanup_code(self, content: str) -> str:
        if content.startswith('```') and content.endswith('```'):
            return '\n'.join(content.split('\n')[1:-1])
        return content.strip(' \n')

    def cleanup_list(self, data: list) -> list:
        return [d for d in data if d is not None and d != '']

    def cleanup_channel_name(self, text: str) -> str:
        converter = {
            ' ': '-',
            '.': '-',
            ',': '-',
            '--': '-'
        }
        for word, replace in converter.items():
            text = text.replace(word, replace)
        return text.lower()

    def convert_backend_type(self, backendType: str) -> str:
        return self.BACKEND_TO_API_CONVERTER.get(backendType)

    def convert_to_backend_type(self, type: str) -> str:
        return self.API_TO_BACKEND_CONVERTER.get(type)

    def convert_backend_to_key(self, backendType: str) -> str:
        return self.BACKEND_TO_KEY_CONVERTER.get(backendType)

    def convert_backend_to_id(self, backendType: str) -> str:
        return self.BACKEND_TO_ID_CONVERTER.get(backendType)

    def convert_variant(self, variants: list) -> list:
        if variants is None:
            return None
        return [
            {
                'name': option['name'],
                'variants': [
                    {
                        'c': variant['channel'],
                        'v': option['tag'],
                        'dE': 0
                    }
                ]
            } for variant in variants for option in variant.get('options', [])
        ]

    def get_item_str(self, item: dict) -> str:
        return '<Item name={0[name]!r} id={0[id]!r}>'.format(
            item
        )

    def get_playlist_str(self, playlist: dict) -> str:
        return '<Playlist name={0[name]!r} id={0[id]!r}>'.format(
            playlist
        )

    def get_variant_str(self, variant: dict) -> str:
        return ('<Variant name={0[name]!r} '
                'channel={1[c]!r} '
                'tag={1[v]!r}>'.format(
                    variant,
                    variant['variants'][0]
                ))

    def get_config_item_id(self, text: str) -> str:
        match = self.config_item_pattern.match(text)
        if match is None:
            return None
        return match.group('id')

    def get_config_playlist_id(self, text: str) -> str:
        match = self.config_playlist_pattern.match(text)
        if match is None:
            return None
        return match.group('id')

    def get_config_variant(self, text: str) -> dict:
        match = self.config_variant_pattern.match(text)
        if match is None:
            return None
        return {
            'name': match.group('name'),
            'variants': [
                {
                    'c': match.group('channel'),
                    'v': match.group('tag'),
                    'dE': 0
                }
            ]
        }

    def setup(self) -> None:
        self.config, self.error_config = self.load_config()
        if self.config is None and self.error_config is None:
            sys.exit(1)
        if self.error_config:
            self.send(
                self.l(
                    'error_keys',
                    '\n'.join(self.error_config),
                    default=(
                        "以下のキーに問題がありました\n{0}\n"
                        "There was an error on keys\n{0}\n"
                    )
                ),
                file=sys.stderr
            )
        self.webhook = WebhookClient(self, self, self.loop, self.http)
        self.webhook.start()
        if self.config['discord']['enabled']:
            self.discord_client = DiscordClient(self, self.config, loop=self.loop)

        if self.isfile(f"{self.lang_dir}/{self.config['lang']}", force_file=True):
            self.localize = self.load_localize(self.config['lang'])
        else:
            self.localize = self.load_localize('en')

        self.commands, self.error_commands = self.load_commands()
        if self.commands is None and self.error_commands is None:
            sys.exit(1)
        if self.error_commands:
            self.send(
                self.l(
                    'error_keys',
                    '\n'.join(self.error_commands),
                    default=(
                        "以下のキーに問題がありました\n{0}\n"
                        "There was an error on keys\n{0}\n"
                    )
                ),
                file=sys.stderr
            )

        if not self.is_error():
            self.send(
                self.l(
                    'load_success',
                    default=(
                        "正常に読み込みが完了しました\n"
                        "Loading successfully finished\n"
                    )
                ),
                color=green
            )
        elif self.config['web']['enabled']:
            self.send(
                self.l(
                    'load_failed_web',
                    default=(
                        "正常に読み込みが完了しませんでした。ファイルを直接修正するか、Webから修正してください\n"
                        "Loading didn't finish normally. Please fix files directly or fix from web\n"
                    )
                ),
                file=sys.stderr
            )
        else:
            self.send(
                self.l(
                    'load_failed',
                    default=(
                        "正常に読み込みが完了しませんでした。ファイルを修正してください\n"
                        "Loading didn't finish normally. Please fix files\n"
                    )
                ),
                file=sys.stderr
            )
            sys.exit(1)

        try:
            self.cosmetic_presets = self.get_cosmetic_presets()
        except (json.decoder.JSONDecodeError, UnicodeDecodeError):
            if self.isfile('cosmetic_presets_old'):
                self.remove('cosmetic_presets_old')
            self.rename('cosmetic_presets', 'cosmetic_presets_old')
            self.cosmetic_presets = {}

    async def aexec(self, body: str, variables: dict) -> Tuple[Any, str, str]:
        body = self.cleanup_code(body)
        stdout = io.StringIO()
        stderr = io.StringIO()

        exc = f"async def __exc__():\n{textwrap.indent(body,'  ')}"
        exec(exc, variables)

        func = variables['__exc__']
        with redirect_stdout(stdout), redirect_stderr(stderr):
            return await func(), stdout.getvalue(), stderr.getvalue()


    def format_item(self, data: dict, mode: str) -> dict:
        if mode == 'BenBot':
            return {
                'id': data['id'],
                'name': data['name'],
                'type': {
                    'value': self.convert_backend_type(data['backendType']),
                    'displayValue': data['shortDescription'],
                    'backendValue': data['backendType']
                },
                'set': data['set'],
                'variants': self.convert_variant(data['variants'])
            }
        elif mode == 'Fortnite-API':
            return {
                'id': data['id'],
                'name': data['name'],
                'type': data['type'],
                'set': data['set']['value'] if data['set'] is not None else None,
                'variants': self.convert_variant(data['variants'])
            }
        elif mode == 'FortniteApi.io':
            return {
                'id': data['id'],
                'name': data['name'],
                'type': {
                    'value': data['type'],
                    'displayValue': (
                        self.l(data['type']).get_text()
                        or data['type']
                    ),
                    'backendValue': self.convert_to_backend_type(data['type'])
                },
                'set': data['set'] if data['set'] else None,
                'variants': None
            }

    def format_items(self, data: list, mode: str) -> list:
        types = [
            'AthenaCharacter',
            'AthenaBackpack',
            'AthenaPet',
            'AthenaPetCarrier',
            'AthenaPickaxe',
            'AthenaDance',
            'AthenaEmoji',
            'AthenaToy'
        ]
        return [item for item in [
            self.format_item(item, mode)
            for item in sorted(data, key=lambda x: x['id'])
        ] if item['type']['backendValue'] in types]

    async def get_item_data(self, lang: str) -> list:
        if self.config['api'] == 'BenBot':
            return self.format_items(await self.http.get(
                'http://benbotfn.tk/api/v1/cosmetics/br',
                params={'lang': lang}
            ), self.config['api'])
        elif self.config['api'] == 'Fortnite-API':
            return self.format_items((await self.http.get(
                'https://fortnite-api.com/v2/cosmetics/br',
                params={'language': lang}
            ))['data'], self.config['api'])
        elif self.config['api'] == 'FortniteApi.io':
            items = (await self.http.get(
                'https://fortniteapi.io/v1/items/list',
                params={'lang': lang},
                headers={'Authorization': self.config['api_key']}
            ))['items']
            return self.format_items(
                sum(
                    [v for k, v in items.items() if k not in [
                        'bannertoken',
                        'bundle',
                        'cosmeticvariant'
                    ]],
                    []
                ),
                self.config['api']
            )

    async def store_item_data(self, lang: str) -> None:
        if self.isfile(f'{self.item_dir}/items_{lang}', force_file=True):
            items = self.load_json(f'{self.item_dir}/items_{lang}', force_file=True)
            items['items'] = CaseInsensitiveDict(items['items'])
        else:
            items = {'api': None, 'items': CaseInsensitiveDict()}
        data = await self.get_item_data(lang)
        if self.config['api'] == 'FortniteApi.io':
            for item in data:
                i = items['items'].get(item['id'])
                if i is None:
                    items['items'][item['id']] = item
                elif i['variants'] is not None:
                    item['variants'] = i['variants']
                    items['items'][item['id']] = item
        else:
            for item in data:
                items['items'][item['id']] = item
        items['api'] = self.config['api']
        self.save_json(
            f'{self.item_dir}/items_{lang}',
            items,
            force_file=True,
            compact=True
        )

    async def get_new_item_data(self, lang: str) -> list:
        if self.config['api'] == 'BenBot':
            return self.format_items(await self.http.get(
                'http://benbotfn.tk/api/v1/newCosmetics',
                params={'lang': lang}
            ), self.config['api'])
        elif self.config['api'] == 'Fortnite-API':
            return self.format_items((await self.http.get(
                'https://fortnite-api.com/v2/cosmetics/br/new',
                params={'language': lang}
            ))['data']['items'], self.config['api'])
        elif self.config['api'] == 'FortniteApi.io':
            return self.format_items((await self.http.get(
                'https://fortniteapi.io/v1/items/upcoming',
                params={'lang': lang},
                headers={'Authorization': self.config['api_key']}
            ))['items'], self.config['api'])

    async def store_new_item_data(self, lang: str) -> None:
        if self.isfile(f'{self.item_dir}/new_items_{lang}', force_file=True):
            items = self.load_json(f'{self.item_dir}/new_items_{lang}', force_file=True)
            items['items'] = CaseInsensitiveDict(items['items'])
        else:
            items = {'api': None, 'items': CaseInsensitiveDict()}
        data = {i['id']: i for i in await self.get_new_item_data(lang)}
        if self.config['api'] == 'FortniteApi.io':
            for item in items['items'].values():
                i = data.get(item['id'])
                if i is None:
                    continue
                if item['variants'] is not None:
                    data[item['id']]['variants'] = item['variants']
        items['api'] = self.config['api']
        self.save_json(
            f'{self.item_dir}/new_items_{lang}',
            {'api': self.config['api'], 'items': data},
            force_file=True,
            compact=True
        )


    def format_playlist(self, data: dict, mode: str) -> dict:
        if mode == 'Fortnite-API':
            return {
                'id': data['id'],
                'name': data['name']
            }
        elif mode == 'FortniteApi.io':
            return {
                'id': f'Playlist_{data["id"]}',
                'name': data['name']
            }

    def format_playlists(self, data: list, mode: str) -> list:
        return [
            self.format_playlist(playlist, mode)
            for playlist in sorted(data, key=lambda x: x['id'])
        ]

    async def get_playlists_data(self, lang: str) -> list:
        if self.config['api'] == 'BenBot':
            return []
        elif self.config['api'] == 'Fortnite-API':
            return self.format_playlists(
                (await self.http.get(
                    'https://fortnite-api.com/v1/playlists',
                    params={'lang': lang}
                ))['data'], self.config['api']
            )
        elif self.config['api'] == 'FortniteApi.io':
            return self.format_playlists(
                (await self.http.get(
                    'https://fortniteapi.io/v1/game/modes',
                    params={'lang': lang},
                    headers={'Authorization': self.config['api_key']}
                ))['modes'], self.config['api']
            )

    async def store_playlists_data(self, lang: str) -> None:
        if self.isfile(f'{self.item_dir}/playlists_{lang}', force_file=True):
            playlists = self.load_json(f'{self.item_dir}/playlists_{lang}', force_file=True)
            playlists['playlists'] = CaseInsensitiveDict(playlists['playlists'])
        else:
            playlists = {'api': None, 'playlists': CaseInsensitiveDict()}
        data = await self.get_playlists_data(lang)
        for playlist in data:
            playlists['playlists'][playlist['id']] = playlist
        playlists['api'] = self.config['api']
        self.save_json(
            f'{self.item_dir}/playlists_{lang}',
            playlists,
            force_file=True,
            compact=True
        )


    async def get_banner_data(self) -> dict:
        if self.config['api'] == 'BenBot':
            data = await self.http.get(
                'https://benbotfn.tk/api/v1/files/search',
                params={
                    'matchMethod': 'starts',
                    'path': 'FortniteGame/Content/Items/BannerIcons/'
                }
            )
            url = 'https://benbotfn.tk/api/v1/exportAsset?path={}&rawIcon=true'
            return {
                'api': self.config['api'],
                'banners': {banner[39:-7]: url.format(banner) for banner in data}
            }
        elif self.config['api'] == 'Fortnite-API':
            data = (await self.http.get(
                'https://fortnite-api.com/v1/banners'
            ))['data']
            return {
                'api': self.config['api'],
                'banners': {banner['id']: banner['images']['icon'] for banner in data}
            }
        elif self.config['api'] == 'FortniteApi.io':
            return {'api': self.config['api'], 'banners': {}}

    async def store_banner_data(self) -> None:
        if self.isfile(f'{self.item_dir}/banners', force_file=True):
            banners = self.load_json(f'{self.item_dir}/banners', force_file=True)
            banners['banners'] = CaseInsensitiveDict(banners['banners'])
        else:
            banners = {'api': None, 'banners': CaseInsensitiveDict()}
        data = await self.get_banner_data()
        for id, image in data.items():
            banners['banners'][id] = image
        banners['api'] = self.config['api']
        self.save_json(f'{self.item_dir}/banners', banners, force_file=True, compact=True)


    async def error_callback(self, client: Client, e: Exception):
        print('error')
        if isinstance(e, fortnitepy.AuthException):
            if 'Invalid device auth details passed.' in e.args[0]:
                self.debug_print_exception(e)
                self.send(
                    self.l(
                        'device_auth_error',
                        client.config['fortnite']['email']
                    ),
                    add_p=self.time,
                    file=sys.stderr
                )
                details = self.get_device_auth_details()
                details.pop(client.config['fortnite']['email'])
                self.save_json('device_auths', details)
            else:
                self.print_exception(e)
                self.send(
                    self.l(
                        'login_failed',
                        client.config['fortnite']['email']
                    ),
                    add_p=self.time,
                    file=sys.stderr
                )
        else:
            self.print_exception(e)
            self.send(
                self.l(
                    'login_failed',
                    client.config['fortnite']['email']
                ),
                add_p=self.time,
                file=sys.stderr
            )

    async def all_ready_callback(self):
        if len(self.clients) > 1:
            await asyncio.gather(*[client.wait_until_ready() for client in self.clients])
            self.send(
                self.l(
                    'all_login'
                ),
                color=green,
                add_p=self.time
            )

    async def update_data(self) -> None:
        # Cosmetics
        tasks = []
        if self.isfile(f"{self.item_dir}/items_{self.config['search_lang']}", force_file=True):
            items = self.load_json(f"{self.item_dir}/items_{self.config['search_lang']}", force_file=True)
            if items['api'] != self.config['api']:
                flag = True
            else:
                flag = self.is_not_edited_for(
                    f"{self.item_dir}/items_{self.config['search_lang']}",
                    datetime.timedelta(hours=2),
                    force_file=True
                )
        else:
            flag = True
        if flag:
            tasks.append(self.loop.create_task(self.store_item_data(self.config['search_lang'])))

        if self.isfile(f"{self.item_dir}/items_{self.config['sub_search_lang']}", force_file=True):
            items = self.load_json(f"{self.item_dir}/items_{self.config['sub_search_lang']}", force_file=True)
            if items['api'] != self.config['api']:
                flag = True
            else:
                flag = self.is_not_edited_for(
                    f"{self.item_dir}/items_{self.config['sub_search_lang']}",
                    datetime.timedelta(hours=2),
                    force_file=True
                )
        else:
            flag = True
        if flag:
            tasks.append(self.loop.create_task(self.store_item_data(self.config['sub_search_lang'])))

        exception = False
        if tasks:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for p in pending:
                if not p.done():
                    p.cancel()
            for d in done:
                if d.exception() is not None:
                    exception = True
                    self.print_exception(d.exception())
            if exception:
                self.send(
                    self.l(
                        'get_item_failed'
                    ),
                    file=sys.stderr
                )
                for lang in (self.config['search_lang'], self.config['sub_search_lang']):
                    if not self.isfile(f'{self.item_dir}/items_{lang}', force_file=True):
                        sys.exit(1)

        # New cosmetics
        tasks = []
        if self.isfile(f"{self.item_dir}/new_items_{self.config['search_lang']}", force_file=True):
            items = self.load_json(f"{self.item_dir}/new_items_{self.config['search_lang']}", force_file=True)
            if items['api'] != self.config['api']:
                flag = True
            else:
                flag = self.is_not_edited_for(
                    f"{self.item_dir}/new_items_{self.config['search_lang']}",
                    datetime.timedelta(hours=2),
                    force_file=True
                )
        else:
            flag = True
        if flag:
            try:
                await self.store_new_item_data(self.config['search_lang'])
            except Exception as e:
                self.print_exception(e)
                self.send(
                    self.l(
                        'get_item_failed'
                    ),
                    file=sys.stderr
                )

        # Playlists
        tasks = []
        if self.isfile(f"{self.item_dir}/playlists_{self.config['search_lang']}", force_file=True):
            playlists = self.load_json(f"{self.item_dir}/playlists_{self.config['search_lang']}", force_file=True)
            if playlists['api'] != self.config['api']:
                flag = True
            else:
                flag = self.is_not_edited_for(
                    f"{self.item_dir}/playlists_{self.config['search_lang']}",
                    datetime.timedelta(hours=2),
                    force_file=True
                )
        else:
            flag = True
        if flag:
            tasks.append(self.loop.create_task(self.store_playlists_data(self.config['search_lang'])))

        if self.isfile(f"{self.item_dir}/playlists_{self.config['sub_search_lang']}", force_file=True):
            playlists = self.load_json(f"{self.item_dir}/playlists_{self.config['sub_search_lang']}", force_file=True)
            if playlists['api'] != self.config['api']:
                flag = True
            else:
                flag = self.is_not_edited_for(
                    f"{self.item_dir}/playlists_{self.config['sub_search_lang']}",
                    datetime.timedelta(hours=2),
                    force_file=True
                )
        else:
            flag = True
        if flag:
            tasks.append(self.loop.create_task(self.store_playlists_data(self.config['sub_search_lang'])))

        exception = False
        if tasks:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for p in pending:
                if not p.done():
                    p.cancel()
            for d in done:
                if d.exception() is not None:
                    exception = True
                    self.print_exception(d.exception())
            if exception:
                self.send(
                    self.l(
                        'get_playlist_failed'
                    ),
                    file=sys.stderr
                )
                for lang in (self.config['search_lang'], self.config['sub_search_lang']):
                    if not self.isfile(f'{self.item_dir}/playlists_{lang}', force_file=True):
                        sys.exit(1)

        # Banner
        if not exception:
            if self.isfile(f'{self.item_dir}/banners', force_file=True):
                banners = self.load_json(f"{self.item_dir}/banners", force_file=True)
                if banners['api'] != self.config['api']:
                    flag = True
                else:
                    flag = self.is_not_edited_for(
                        f'{self.item_dir}/banners',
                        datetime.timedelta(hours=2),
                        force_file=True
                    )
            else:
                flag = True
            if flag:
                await self.store_banner_data()

    def load_data(self) -> None:
        self.main_items = CaseInsensitiveDict(self.load_json(
            f'{self.item_dir}/items_{self.config["search_lang"]}',
            force_file=True
        )['items'])
        self.sub_items = CaseInsensitiveDict(self.load_json(
            f'{self.item_dir}/items_{self.config["sub_search_lang"]}',
            force_file=True
        )['items'])
        self.new_items = CaseInsensitiveDict(self.load_json(
            f'{self.item_dir}/new_items_{self.config["search_lang"]}',
            force_file=True
        )['items'])
        self.main_playlists = CaseInsensitiveDict(self.load_json(
            f'{self.item_dir}/playlists_{self.config["search_lang"]}',
            force_file=True
        )['playlists'])
        self.sub_playlists = CaseInsensitiveDict(self.load_json(
            f'{self.item_dir}/playlists_{self.config["sub_search_lang"]}',
            force_file=True
        )['playlists'])
        self.banners = CaseInsensitiveDict(self.load_json(
            f'{self.item_dir}/banners',
            force_file=True
        )['banners'])

    def fix_config(self, config: dict) -> None:
        config['fortnite']['party']['privacy'] = getattr(
            PartyPrivacy,
            config['fortnite']['party']['privacy'].upper()
        )
        config['fortnite']['platform'] = fortnitepy.Platform(
            config['fortnite']['platform'].upper()
        )
        for num, channel in enumerate(config['discord']['channels']):
            config['discord']['channels'][num] = self.cleanup_channel_name(channel)
        if config['fortnite']['ng_platforms'] is not None:
            for num, ng_platform in enumerate(config['fortnite']['ng_platforms']):
                config['fortnite']['ng_platforms'][num] = fortnitepy.Platform(
                    ng_platform.upper()
                )
        self.fix_cosmetic_config(config)

    def fix_config_all(self) -> None:
        for num, channel in enumerate(self.config['discord']['channels']):
            self.config['discord']['channels'][num] = self.cleanup_channel_name(channel)
        for config in self.config['clients']:
            self.fix_config(config)

    def fix_cosmetic_config(self, config: dict) -> None:
        if config['fortnite']['party']['playlist']:
            if self.get_config_playlist_id(config['fortnite']['party']['playlist']) is None:
                playlist = self.searcher.get_playlist(
                    config['fortnite']['party']['playlist']
                )
                if playlist is None:
                    playlists = self.searcher.search_playlist_name_id(
                        config['fortnite']['party']['playlist']
                    )
                    if len(playlists) != 0:
                        playlist = playlists[0]
                if playlist is not None:
                    config['fortnite']['party']['playlist'] = (
                        self.get_playlist_str(playlist)
                    )
                else:
                    self.send(
                        self.l(
                            'not_found',
                            self.l('playlist'),
                            config['fortnite']['party']['playlist']
                        ),
                        add_p=self.time,
                        file=sys.stderr
                    )

        for item in ['AthenaCharacter',
                     'AthenaBackpack,AthenaPet,AthenaPetCarrier',
                     'AthenaPickaxe',
                     'AthenaDance,AthenaEmoji,AthenaToy']:
            lang_key = self.convert_backend_type(item.split(",")[0])
            for prefix in ['', 'join_', 'leave_']:
                key = f'{prefix}{lang_key}'
                style_key = f'{key}_style'
                if not config['fortnite'][key]:
                    continue

                def fix_cosmetic_style_config():
                    if 'AthenaDance' in item or not config['fortnite'][style_key]:
                        return
                    for num, style_info in enumerate(config['fortnite'][style_key]):
                        if self.get_config_variant(style_info) is not None:
                            continue
                        styles = self.searcher.search_style(
                            self.get_config_item_id(config['fortnite'][key]),
                            style_info
                        )
                        if len(styles) != 0:
                            style = styles[0]
                            config['fortnite'][style_key][num] = (
                                self.get_variant_str(style)
                            )
                        else:
                            self.send(
                                self.l(
                                    'not_found',
                                    self.l('style'),
                                    config['fortnite'][key]
                                ),
                                add_p=self.time,
                                file=sys.stderr
                            )

                if self.get_config_item_id(config['fortnite'][key]) is not None:
                    fix_cosmetic_style_config()
                    continue
                if config['fortnite'][key]:
                    cosmetic = self.searcher.get_item(
                        config['fortnite'][key]
                    )
                    if cosmetic is None:
                        cosmetics = self.searcher.search_item_name_id(
                            config['fortnite'][key],
                            item
                        )
                        if len(cosmetics) != 0:
                            cosmetic = cosmetics[0]
                    if cosmetic is not None:
                        config['fortnite'][key] = (
                            self.get_item_str(cosmetic)
                        )
                        fix_cosmetic_style_config()
                    else:
                        self.send(
                            self.l(
                                'not_found',
                                self.l(lang_key),
                                config['fortnite'][key]
                            ),
                            add_p=self.time,
                            file=sys.stderr
                        )

            key = f'ng_{lang_key}s'
            if not config['fortnite'][key]:
                continue
            for num, cosmetic in enumerate(config['fortnite'][key]):
                if self.get_config_item_id(cosmetic) is not None:
                    continue
                if cosmetic:
                    cosmetic = self.searcher.get_item(
                        cosmetic
                    )
                    if cosmetic is None:
                        cosmetics = self.searcher.search_item_name_id(
                            cosmetic,
                            item
                        )
                        if len(cosmetics) != 0:
                            cosmetic = cosmetics[0]
                    if cosmetic is not None:
                        config['fortnite'][key][num] = (
                            self.get_item_str(cosmetic)
                        )
                    else:
                        self.send(
                            self.l(
                                'not_found',
                                self.l(lang_key),
                                cosmetic
                            ),
                            add_p=self.time,
                            file=sys.stderr
                        )

    def fix_cosmetic_config_all(self) -> None:
        for config in self.config['clients']:
            self.fix_cosmetic_config(config)

    async def reboot(self) -> None:
        await self.close()
        os.execv(sys.executable, ['python', f'"{os.path.abspath(sys.argv[0])}"', *sys.argv[1:]])

    async def close(self) -> None:
        if self.server is not None:
            await self.server.close()

        await fortnitepy.close_multiple(
            self.clients
        )

    async def start(self) -> None:
        self.send(
            self.l('credit'),
            color=cyan
        )
        self.send(
            (f'{self.l("loglevel", self.l("loglevel_" + self.config["loglevel"]))}\n\n'
             f'Python {platform.python_version()}\n'
             f'fortnitepy {fortnitepy.__version__}\n'
             f'discord.py {discord.__version__}\n'
             f'Sanic {sanic.__version__}\n'),
            color=green
        )

        if self.config['debug']:
            logger = logging.getLogger('fortnitepy.auth')
            logger.setLevel(level=logging.DEBUG)
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter('\u001b[35m %(asctime)s:%(levelname)s:%(name)s: %(message)s \u001b[0m'))
            logger.addHandler(handler)

            logger = logging.getLogger('fortnitepy.http')
            logger.setLevel(level=logging.DEBUG)
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter('\u001b[35m %(asctime)s:%(levelname)s:%(name)s: %(message)s \u001b[0m'))
            logger.addHandler(handler)

            logger = logging.getLogger('fortnitepy.xmpp')
            logger.setLevel(level=logging.DEBUG)
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter('\u001b[35m %(asctime)s:%(levelname)s:%(name)s: %(message)s \u001b[0m'))
            logger.addHandler(handler)

        version = sys.version_info
        if version.minor < 7 or version.minor > 7:
            self.send(
                self.l('not_recommended_version'),
                platform.python_version()
            )

        if not self.is_error():
            self.send(
                self.l(
                    'updating',
                ),
                add_p=self.time
            )
            await self.update_data()
            self.load_data()
            self.searcher = Searcher(
                self.main_items,
                self.sub_items,
                self.main_playlists,
                self.sub_playlists,
                True,
                False
            )
            self.send(
                self.l(
                    'booting',
                ),
                add_p=self.time
            )
        if self.config['web']['enabled']:
            if not self.config['web']['access_log']:
                logger = getLogger('sanic.root')
                logger.setLevel(WARNING)
            try:
                self.server = await self.web.create_server(
                    host=self.config['web']['ip'],
                    port=self.config['web']['port'],
                    access_log=self.config['web']['access_log'],
                    return_asyncio_server=True
                )
                await self.server.start_serving()
            except OSError as e:
                self.debug_print_exception(e)
                self.send(
                    self.l(
                        'web_already_running'
                    ),
                    add_p=self.time,
                    file=sys.stderr
                )
            else:
                self.send(
                    self.l(
                        'web_running',
                        f"http://{self.config['web']['ip']}:{self.config['web']['port']}"
                    ),
                    color=green,
                    add_p=self.time
                )

        if not self.is_error():
            self.fix_config_all()
            self.save_json('config', self.config)
            try:
                device_auths = self.get_device_auth_details()
            except (json.decoder.JSONDecodeError, UnicodeDecodeError):
                if self.isfile('device_auths_old'):
                    self.remove('device_auths_old')
                self.rename('device_auths', 'device_auths_old')
                device_auths = {}
            for num, config in enumerate(self.config['clients']):
                device_auth_details = device_auths.get(config['fortnite']['email'].lower(), {})
                if not device_auth_details:
                    device_auth_details = await self.auth.authenticate(config['fortnite']['email'])
                    self.store_device_auth_details(config['fortnite']['email'], device_auth_details)
                party_meta = []
                if config['fortnite']['party']['playlist']:
                    party_meta.append(partial(
                        MyClientParty.set_playlist,
                        playlist=(self.get_config_playlist_id(config['fortnite']['party']['playlist'])
                                  or config['fortnite']['party']['playlist'])
                    ))
                if config['fortnite']['party']['disable_voice_chat']:
                    party_meta.append(partial(
                        MyClientParty.disable_voice_chat
                    ))

                member_meta = []
                items = [
                    'AthenaCharacter',
                    'AthenaBackpack',
                    'AthenaPickaxe',
                    'AthenaDance'
                ]
                for item in items:
                    conf = self.convert_backend_type(item)
                    if config['fortnite'][conf]:
                        variants = []
                        if item != 'AthenaDance' and config['fortnite'][f'{conf}_style'] is not None:
                            for style in config['fortnite'][f'{conf}_style']:
                                variant = self.get_config_variant(style)
                                if variant is not None:
                                    variants.extend(variant['variants'])
                        member_meta.append(partial(
                            MyClientPartyMember.set_outfit,
                            asset=(self.get_config_item_id(config['fortnite'][conf])
                                   or config['fortnite'][conf]),
                            variants=variants
                        ))

                avatar = fortnitepy.kairos.get_random_default_avatar()
                background_colors = (
                    config['fortnite']['avatar_color'].split(',')
                    if ',' in config['fortnite']['avatar_color'] else
                    getattr(fortnitepy.KairosBackgroundColorPreset, config['fortnite']['avatar_color'].upper())
                )
                client = Client(
                    self,
                    config,
                    num,
                    auth=fortnitepy.DeviceAuth(
                        **device_auth_details
                    ),
                    avatar=fortnitepy.Avatar(
                        asset=(
                            config['fortnite']['avatar_id']
                            or avatar.asset
                        ),
                        background_colors=(
                            background_colors
                            if config['fortnite']['avatar_color'] else
                            avatar.background_colors
                        )
                    ),
                    status=config['fortnite']['status'],
                    platform=config['fortnite']['platform'],
                    loop=self.loop
                )

                client.default_party_config = fortnitepy.DefaultPartyConfig(
                    cls=MyClientParty,
                    privacy=config['fortnite']['party']['privacy'],
                    team_change_allowed=config['fortnite']['party']['allow_swap'],
                    max_size=config['fortnite']['party']['max_size'],
                    meta=party_meta
                )
                client.default_party_member_config = fortnitepy.DefaultPartyMemberConfig(
                    cls=MyClientPartyMember,
                    meta=member_meta
                )
                self.clients.append(client)

            tasks = [
                fortnitepy.start_multiple(
                    self.clients,
                    shutdown_on_error=False,
                    error_callback=self.error_callback,
                    all_ready_callback=self.all_ready_callback
                )
            ]
            if self.discord_client is not None:
                tasks.append(self.discord_client.start())

            await asyncio.gather(*tasks)
        else:
            while True:
                await asyncio.sleep(0.1)

    async def process_command(self, message: MyMessage) -> None:
        if not message.args:
            return
        for client in self.clients:
            self.loop.create_task(client.process_command(message))
