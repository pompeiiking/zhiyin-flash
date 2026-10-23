"""User-bound previews and atomic import receipts; not a read cache."""
from abc import ABC, abstractmethod


class ChsiImportRepository(ABC):
    @abstractmethod
    async def create(self, record: dict) -> None: ...

    @abstractmethod
    def locked(self, user_id: str, preview_id: str):
        """Transaction and lock shared with the profile repository."""

    @abstractmethod
    async def finish(self, user_id: str, preview_id: str, receipt: dict) -> None: ...

    @abstractmethod
    async def cleanup(self) -> int: ...
