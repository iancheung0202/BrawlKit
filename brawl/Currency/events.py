from collections import defaultdict

handlers = defaultdict(dict)


def on(name):
    def add(handler):
        handlers[name][handler.__qualname__] = handler
        return handler

    return add


def listen(name, handler):
    handlers[name][handler.__qualname__] = handler


async def emit(name, user_id, **data):
    for handler in list(handlers[name].values()):
        try:
            await handler(user_id, **data)
        except Exception as error:
            print(f"Error in {name} handler {handler.__qualname__}: {error}")


async def setup(bot):
    pass
