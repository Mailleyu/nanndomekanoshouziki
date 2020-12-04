# -*- coding: utf-8 -*-
from typing import Optional, List

import jaconv
from pykakasi import kakasi


class CaseInsensitiveDict(dict):
    def __init__(self, v=None, **kwarg):
        super().__init__(self.casefold(v, **kwarg))

    def casefold(self, v, **kwarg):
        data = {}
        if v is not None:
            if isinstance(v, dict):
                for k, v in v.items():
                    if isinstance(k, str):
                        k = k.casefold()
                    data[k] = v
            else:
                for k, v in v:
                    if isinstance(k, str):
                        k = k.casefold()
                    data[k] = v
        for k, v in kwarg.items():
            if isinstance(k, str):
                k = k.casefold()
            data[k] = v
        return data

    def __contains__(self, k):
        if isinstance(k, str):
            k = k.casefold()
        return super().__contains__(k)

    def __delitem__(self, k):
        if isinstance(k, str):
            k = k.casefold()
        return super().__delitem__(k)

    def __getitem__(self, k):
        if isinstance(k, str):
            k = k.casefold()
        return super().__getitem__(k)

    def get(self, k, default=None):
        if isinstance(k, str):
            k = k.casefold()
        return super().get(k, default)

    def pop(self, k, default=None):
        if isinstance(k, str):
            k = k.casefold()
        return super().pop(k, default)

    def update(self, v=None, **kwarg):
        super().update(self.casefold(v, **kwarg))

    def __setitem__(self, k, v):
        if isinstance(k, str):
            k = k.casefold()
        super().__setitem__(k, v)


class Searcher:
    def __init__(self, main_items: CaseInsensitiveDict, sub_items: CaseInsensitiveDict,
                 main_playlists: CaseInsensitiveDict, sub_playlists: CaseInsensitiveDict,
                 case_insensitive: bool, convert_kanji: bool) -> None:
        self.main_items = main_items
        self.sub_items = sub_items
        self.main_playlists = main_playlists
        self.sub_playlists = sub_playlists
        self.case_insensitive = case_insensitive
        self.convert_kanji = convert_kanji
        self.kakasi = kakasi()
        self.kakasi.setMode('J', 'H')
        self.converter = self.kakasi.getConverter()

    def get_item(self, id: str) -> Optional[dict]:
        return self.main_items.get(id)

    def search_item(self, mode: str, text: str,
                    item: Optional[str] = None) -> List[dict]:
        if self.case_insensitive:
            text = jaconv.kata2hira(text.casefold())
        if self.convert_kanji:
            text = self.converter.do(text)

        result = []

        def find(cosmetic):
            if (item and cosmetic['type']['backendValue'] not in item.split(',')
                    or cosmetic['name'] is None):
                return
            if mode == 'name':
                name = cosmetic['name']
                if self.case_insensitive:
                    name = jaconv.kata2hira(cosmetic['name'].casefold())
                if self.convert_kanji:
                    name = self.converter.do(name)
                if text in name:
                    result.append(cosmetic)
            elif mode == 'id':
                if text in (cosmetic['id'].casefold()):
                    result.append(cosmetic)
            elif mode == 'set':
                if cosmetic.get('set') is None:
                    return
                name = cosmetic['name']
                if self.case_insensitive:
                    name = jaconv.kata2hira(name.casefold())
                if self.convert_kanji:
                    name = self.converter.do(name)
                if text in name:
                    result.append(cosmetic)

        for cosmetic in self.main_items.values():
            find(cosmetic)
        if len(result) == 0:
            for cosmetic in self.sub_items.values():
                find(cosmetic)

        return result

    def search_item_name_id(self, text: str,
                            item: Optional[str] = None) -> List[dict]:
        items = self.search_item('name', text, item)
        if len(items) == 0:
            items = self.search_item('id', text, item)

        return items

    def get_style(self, id: str) -> List[dict]:
        item = self.main_items.get(id)
        if item is None or item.get('variants') is None:
            return []
        return item['variants']

    def search_style(self, id: str, text: str) -> List[dict]:
        if self.case_insensitive:
            text = jaconv.kata2hira(text.casefold())
        if self.convert_kanji:
            text = self.converter.do(text)

        styles = self.get_style(id)

        result = []

        for style in styles:
            name = style['name']
            if self.case_insensitive:
                name = jaconv.kata2hira(name.casefold())
            if self.convert_kanji:
                name = self.converter.do(name)
            if text in name:
                result.append(style)

        return result


    def get_playlist(self, id: str) -> Optional[dict]:
        return self.main_playlists.get(id)

    def search_playlist(self, mode: str, text: str) -> List[dict]:
        if self.case_insensitive:
            text = jaconv.kata2hira(text.casefold())
        if self.convert_kanji:
            text = self.converter.do(text)

        result = []

        def find(playlist):
            if mode == 'name':
                if self.case_insensitive:
                    name = jaconv.kata2hira(playlist['name'].casefold())
                else:
                    name = playlist['name']
                if self.convert_kanji:
                    name = self.converter.do(name)
                if text in name:
                    result.append(playlist)
            elif mode == 'id':
                if text in playlist['id'].casefold():
                    result.append(playlist)

        for playlist in self.main_playlists.values():
            find(playlist)
        if len(result) == 0:
            for playlist in self.sub_playlists.values():
                find(playlist)

        return result

    def search_playlist_name_id(self, text: str) -> List[dict]:
        playlists = self.search_playlist('name', text)
        if len(playlists) == 0:
            playlists = self.search_playlist('id', text)

        return playlists
