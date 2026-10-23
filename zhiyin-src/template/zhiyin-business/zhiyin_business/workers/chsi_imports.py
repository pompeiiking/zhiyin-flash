from zhiyin_kernel.worker import Worker


class ChsiImportCleanupWorker(Worker):
    name = "chsi_import_cleanup"
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, records):
        self.records = records

    async def run_once(self):
        return await self.records.cleanup()
