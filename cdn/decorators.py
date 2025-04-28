from functools import wraps


def cdn_cache(cache_get_function, cache_set_function):
    def decorator(func):
        @wraps(func)
        def wrapper(self, uuid: str, *args, **kwargs):
            # Try to get from cache first
            result = cache_get_function(self, uuid)
            if result is not None:
                return result

            # Otherwise, call the real function
            result = func(self, uuid, *args, **kwargs)

            # Optionally set result to cache
            if result is not None:
                cache_set_function(self, uuid, result)

            return result

        return wrapper

    return decorator
