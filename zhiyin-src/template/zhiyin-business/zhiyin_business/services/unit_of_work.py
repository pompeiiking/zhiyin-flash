"""Keep content, version snapshots and outbox events in one database commit."""
from contextlib import asynccontextmanager
from functools import wraps


@asynccontextmanager
async def transaction(repository):
    factory = getattr(repository, "transaction", None)
    if factory is None:
        yield
    else:
        async with factory():
            yield


def atomic_repository(attribute):
    def decorate(method):
        @wraps(method)
        async def call(self, *args, **kwargs):
            async with transaction(getattr(self, attribute)):
                return await method(self, *args, **kwargs)
        return call
    return decorate
