from zhiyin_kernel.worker import Worker


class ProfileEvidenceWorker(Worker):
    name = 'profile_evidence'
    IMPLEMENTATION_STATUS = 'wired'

    def __init__(self, service):
        self.service = service

    async def run_once(self):
        return await self.service.run_once()
