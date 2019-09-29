import inspect
import asyncio
import enum
import json
import time

from functools import wraps

from lru import LRU
from coc import Cache, SearchClan, SearchPlayer

def _wrap_and_store_coroutine(cache, key, coro):
    async def func():
        value = await coro
        cache[key] = value
        return value
    return func()

def _wrap_new_coroutine(value):
    async def new_coroutine():
        return value
    return new_coroutine()

class ExpiringCache(dict):
    def __init__(self, seconds):
        self.__ttl = seconds
        super().__init__()

    def __verify_cache_integrity(self):
        # Have to do this in two steps...
        current_time = time.monotonic()
        to_remove = [k for (k, (v, t)) in self.items() if current_time > (t + self.__ttl)]
        for k in to_remove:
            del self[k]

    def __getitem__(self, key):
        self.__verify_cache_integrity()
        return super().__getitem__(key)

    def __setitem__(self, key, value):
        super().__setitem__(key, (value, time.monotonic()))

class Strategy(enum.Enum):
    lru = 1
    raw = 2
    timed = 3
    redis = 4

def cache(maxsize=128, strategy=Strategy.redis, ignore_kwargs=False):
    def decorator(func):
        if strategy is Strategy.lru:
            _internal_cache = LRU(maxsize)
            _stats = _internal_cache.get_stats
        elif strategy is Strategy.raw:
            _internal_cache = {}
            _stats = lambda: (0, 0)
        elif strategy is Strategy.timed:
            _internal_cache = ExpiringCache(maxsize)
            _stats = lambda: (0, 0)
        else:
            _internal_cache = None
            _stats = lambda: (0, 0)

        def _make_key(args, kwargs):
            # this is a bit of a cluster fuck
            # we do care what 'self' parameter is when we __repr__ it
            def _true_repr(o):
                if o.__class__.__repr__ is object.__repr__:
                    return f'<{o.__class__.__module__}.{o.__class__.__name__}>'
                return repr(o)

            key = [ f'{func.__module__}.{func.__name__}' ]
            key.extend(_true_repr(o) for o in args)
            if not ignore_kwargs:
                for k, v in kwargs.items():
                    # note: this only really works for this use case in particular
                    # I want to pass asyncpg.Connection objects to the parameters
                    # however, they use default __repr__ and I do not care what
                    # connection is passed in, so I needed a bypass.
                    if k == 'connection':
                        continue

                    key.append(_true_repr(v))

            return ':'.join(key)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            redis = args[0].bot.redis

            key = _make_key(args, kwargs)

            value = await redis.get(key, encoding='utf-8')

            if not value:
                value = await func(*args, **kwargs)
                if not value:
                    return

                await redis.set(key, value)
                return value
            else:
                return value

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = _make_key(args, kwargs)
            try:
                value = _internal_cache[key]
            except KeyError:
                value = func(*args, **kwargs)

                if inspect.isawaitable(value):
                    return _wrap_and_store_coroutine(_internal_cache, key, value)

                _internal_cache[key] = value
                return value
            else:
                if asyncio.iscoroutinefunction(func):
                    return _wrap_new_coroutine(value)
                return value

        def _invalidate(*args, **kwargs):
            try:
                del _internal_cache[_make_key(args, kwargs)]
            except KeyError:
                return False
            else:
                return True

        async def async_invalidate(*args, **kwargs):
            return await args[0].bot.redis.delete(_make_key(args, kwargs))

        def _invalidate_containing(key):
            to_remove = []
            for k in _internal_cache.keys():
                if key in k:
                    to_remove.append(k)
            for k in to_remove:
                try:
                    del _internal_cache[k]
                except KeyError:
                    continue

        if strategy is Strategy.redis:
            wrap = async_wrapper
            wrap.invalidate = async_invalidate

        else:
            wrap = wrapper
            wrap.invalidate = _invalidate

        wrap.cache = _internal_cache
        wrap.get_key = lambda *args, **kwargs: _make_key(args, kwargs)
        wrap.get_stats = _stats
        wrap.invalidate_containing = _invalidate_containing
        return wrap

    return decorator


class COCCustomCache(Cache):
    @staticmethod
    def create_default_cache(max_size, ttl):
        return

    @staticmethod
    def make_key(cache_type, key):
        return f'{cache_type}:{key}'

    @staticmethod
    def object_type(cache_type):
        lookup = {
            'search_clans': SearchClan,
            'search_players': SearchPlayer
        }
        return lookup[cache_type]

    async def get(self, cache_type, key, new_key=True):
        if new_key:
            key = self.make_key(cache_type, key)

        value = await self.client.redis.get(key, encoding='utf-8')
        if not value:
            return None
        value = json.loads(value)

        if cache_type == 'search_clans':
            return self.object_type(cache_type)(data=value, client=self.client)
        if cache_type == 'events':
            return [value[0], *(self.object_type(cache_type)(data=n, http=self.client.http) for n in value[1:])]
        return self.object_type(cache_type)(data=value, http=self.client.http)

    async def set(self, cache_type, key, value, new_key=True):
        if new_key:
            key = self.make_key(cache_type, key)
        value = getattr(value, '_data', value)
        if isinstance(value, list):
            value = [json.dumps(getattr(n, '_data', n)) for n in value]

        value = json.dumps(value)

        await self.client.redis.set(key, value)

    async def pop(self, cache_type, key, new_key=True):
        if new_key:
            key = self.make_key(cache_type, key)
        value = await self.client.redis.lpop(key, encoding='utf-8')
        if not value:
            return None

        if cache_type == 'search_clans':
            return self.object_type(cache_type)(data=value, client=self.client)
        return self.object_type(cache_type)(data=value, http=self.client.http)

    async def keys(self, cache_type, limit=0):
        cur, keys = await self.client.redis.scan(match=f'{cache_type}*')
        return (str(n) for n in keys)

    async def values(self, cache_type):
        keys = await self.keys(cache_type)

        return (self.get(cache_type, k, new_key=False) for k in keys
                if self.get(cache_type, k, new_key=False))

    async def items(self, cache_type):
        keys = await self.keys(cache_type)
        return ((k, self.get(cache_type, k, new_key=False)) for k in keys
                if self.get(cache_type, k, new_key=False))

    async def clear(self, cache_type):
        await self.client.redis.flushdb()

    async def get_limit(self, cache_type, limit: int = None):
        keys = await self.keys(cache_type, limit=limit)
        return ((k, self.get(cache_type, k, new_key=False)) for k in keys
                if self.get(cache_type, k, new_key=False))


