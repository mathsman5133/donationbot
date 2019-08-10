import functools
import inspect

from collections import OrderedDict


def cache(max_size=128, arg_offset=0):
    """
    LRU cache implementation for coroutines.
    :param max_size:
    Specifies the maximum size the cache should have.
    Once it exceeds the maximum size, keys are deleted in FIFO order.
    :param arg_offset:
    The offset that should be applied to the coroutine's arguments
    when creating the cache key. Defaults to `0`.
    """

    # Assign the cache to the function itself so we can clear it from outside.
    cache._cache = OrderedDict()

    def decorator(function):
        def _make_key(args, kwargs):
            key = [f'{function.__module__}.{function.__name__}']
            key.extend(str(n) for n in args[arg_offset:])
            for k, v in kwargs:
                key.append(str(k))
                key.append(str(v))

            return ':'.join(key)

        def _invalidate(args, kwargs):
            try:
                del cache._cache[_make_key(args, kwargs)]
            except KeyError:
                return False
            else:
                return True

        @functools.wraps(function)
        async def wrapper(*args, **kwargs):
            key = _make_key(args, kwargs)

            value = cache._cache.get(key)
            if value is None:
                if len(cache._cache) > max_size:
                    cache._cache.popitem(last=False)

                cache._cache[key] = await function(*args, **kwargs)
            return cache._cache[key]

        wrapper.cache = cache._cache
        wrapper.get_key = lambda *args, **kwargs: _make_key(args, kwargs)
        wrapper.invalidate = _invalidate
        return wrapper
    return decorator
