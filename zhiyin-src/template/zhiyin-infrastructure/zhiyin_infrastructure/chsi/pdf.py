"""Bounded PDF extraction in a killable subprocess. Never persists the upload."""
import asyncio
import json
import os
import sys

from zhiyin_data_sdk.gateways.chsi import ChsiReport
from zhiyin_kernel.errors import InvalidRequest


class ChsiPdfReader:
    IMPLEMENTATION_STATUS = "wired"

    def __init__(self, *, timeout=10):
        self.timeout = timeout
        self._slots = asyncio.Semaphore(2)

    async def read(self, data: bytes) -> ChsiReport:
        if not data or len(data) > 2_000_000:
            raise InvalidRequest("请上传不超过 2MB 的学籍报告 PDF。")
        if not data.startswith(b"%PDF-"):
            raise InvalidRequest("文件不是有效 PDF，请重新下载学信网原版报告。")
        async with self._slots:
            env = dict(os.environ)
            env["PYTHONPATH"] = os.pathsep.join(sys.path)
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "zhiyin_infrastructure.chsi.pdf_worker",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, env=env)
            try:
                output, _ = await asyncio.wait_for(proc.communicate(data), self.timeout)
                if proc.returncode != 0 or len(output) > 100_000:
                    raise InvalidRequest("PDF 读取失败，请重新下载学信网原版报告。")
                result = json.loads(output)
                if "error" in result:
                    raise InvalidRequest(result["error"])
                return ChsiReport.model_validate(result)
            except asyncio.TimeoutError as exc:
                raise InvalidRequest("PDF 解析超时，请重新下载原版报告后重试。") from exc
            except (ValueError, KeyError) as exc:
                raise InvalidRequest("PDF 读取失败，请重新下载原版报告。") from exc
            finally:
                if proc.returncode is None:
                    proc.kill()
                await proc.wait()
