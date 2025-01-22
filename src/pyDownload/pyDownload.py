import asyncio
import logging
import aiofiles
import aiohttp
from typing import Any, Callable, Optional, Dict, List, Tuple
from enum import Enum

from attr import dataclass

logger = logging.getLogger(__name__)


class DownloadStatus(Enum):
    UNKNOWN_SIZE = "无法确定大小"
    DOWNLOADING = "下载中"
    CHUNK_DOWNLOADING = "分块下载中"
    COMPLETED = "下载完成"
    FAILED = "下载失败"
    RETRYING = "正在重试"


@dataclass
class chunk_download_status:
    retries: int = 0
    total_downloaded: int = 0
    total_downloaded_lock = asyncio.Lock()
    finished_chunks: int = 0
    finished_chunks_lock = asyncio.Lock()
    total_length: int = 0
    num_chunks: int = 0


class downloadManager:
    _instance: Optional["downloadManager"] = None
    _initialized: bool = False

    def __new__(cls, *args: Any, **kwargs: Any):
        if not cls._instance:
            cls._instance = super(downloadManager, cls).__new__(cls)
        return cls._instance

    def __init__(
        self,
        maxTasks: int = 5,
        max_retries: int = 5,
        chunk_size: int = 4 * 1024 * 1024,
        iter_chunk_size: int = 4 * 1024,
    ):
        if self._initialized:
            return
        self.maxTasks = maxTasks
        self.max_retries = max_retries
        self.chunk_size = chunk_size
        self.iter_chunk_size = iter_chunk_size
        self._initialized = True

        self.init()

    def init(self):
        self.progress_queue: asyncio.Queue[Tuple[str, DownloadStatus, str]] = (
            asyncio.Queue()
        )
        self.downloadStatus: Dict[str, Tuple[DownloadStatus, str]] = {}
        self.downloadTasks: List[asyncio.Task[None]] = []
        self.monitor_task = asyncio.create_task(self.monitor_progress())
        self.semaphore = asyncio.Semaphore(self.maxTasks)

    @staticmethod
    def default_monitor_logger(
        download_name: str, status: DownloadStatus, message: str
    ):
        match status:
            case DownloadStatus.UNKNOWN_SIZE:
                logger.warn(f"{download_name}: {status} - {message}")
            case DownloadStatus.DOWNLOADING | DownloadStatus.CHUNK_DOWNLOADING:
                logger.debug(f"{download_name}: {status} - {message}")
            case DownloadStatus.COMPLETED:
                logger.info(f"{download_name}: {status} - {message}")
            case DownloadStatus.FAILED | DownloadStatus.RETRYING:
                logger.error(f"{download_name}: {status} - {message}")

    async def monitor_progress(
        self,
        func: Callable[[str, DownloadStatus, str], None] = default_monitor_logger,
    ):
        while True:
            download_name, status, message = await self.progress_queue.get()
            func(download_name, status, message)
            self.downloadStatus[download_name] = (status, message)

    async def create_download(self, url: str, file_path: str):
        download_name = f"{url} ==> {file_path}"
        async with self.semaphore:
            task = asyncio.create_task(self._download(url, file_path, download_name))
            self.downloadTasks.append(task)

    async def _download(self, url: str, file_path: str, download_name: str):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(60)
                ) as response:
                    total_length = response.headers.get("content-length")

                    if total_length is None:  # no content length header
                        await self.progress_queue.put(
                            (download_name, DownloadStatus.UNKNOWN_SIZE, "无法确定大小")
                        )
                        return

                    total_length = int(total_length)

                    # Check if server supports range requests
                    range_support = response.headers.get("accept-ranges") == "bytes"

                    if range_support:
                        await self._download_in_chunks(
                            session, url, file_path, download_name, total_length
                        )
                    else:
                        await self._download_single(
                            session, url, file_path, download_name, total_length
                        )
        except Exception as e:
            await self.progress_queue.put(
                (download_name, DownloadStatus.FAILED, f"下载失败: {str(e)}")
            )

    async def _download_in_chunks(
        self,
        session: aiohttp.ClientSession,
        url: str,
        file_path: str,
        download_name: str,
        total_length: int,
    ):
        num_chunks = (total_length + self.chunk_size - 1) // self.chunk_size
        chunk_ranges = [
            (
                i * self.chunk_size,
                min((i + 1) * self.chunk_size, total_length) - 1,
            )
            for i in range(num_chunks)
        ]

        # Create a shared variable to track total downloaded bytes
        chunk_status = chunk_download_status(
            total_length=total_length,
            num_chunks=num_chunks,
        )

        async with aiofiles.open(file_path, "wb") as _f:
            pass

        chunk_tasks = [
            asyncio.create_task(
                self._download_chunk(
                    session,
                    url,
                    file_path,
                    download_name,
                    start,
                    end,
                    chunk_status,
                )
            )
            for start, end in chunk_ranges
        ]

        await asyncio.gather(*chunk_tasks)

    async def _download_chunk(
        self,
        session: aiohttp.ClientSession,
        url: str,
        file_path: str,
        download_name: str,
        start: int,
        end: int,
        chunk_status: chunk_download_status,
    ):
        headers = {"Range": f"bytes={start}-{end}"}
        while chunk_status.retries < self.max_retries:
            try:
                async with session.get(
                    url, headers=headers, timeout=aiohttp.ClientTimeout(60)
                ) as response:
                    if response.status != 206:  # Partial Content
                        raise Exception(f"Unexpected status code: {response.status}")

                    async with aiofiles.open(file_path, "r+b") as f:
                        await f.seek(start)
                        dl = 0
                        async for data in response.content.iter_chunked(
                            self.iter_chunk_size
                        ):
                            chunk_size = len(data)
                            dl += chunk_size
                            await f.write(data)

                            # Update total downloaded bytes
                            async with chunk_status.total_downloaded_lock:
                                chunk_status.total_downloaded += chunk_size
                                done = int(
                                    50
                                    * chunk_status.total_downloaded
                                    / chunk_status.total_length
                                )
                                await self.progress_queue.put(
                                    (
                                        download_name,
                                        DownloadStatus.CHUNK_DOWNLOADING,
                                        f"[{'=' * done}{' ' * (50 - done)}] {chunk_status.total_downloaded / chunk_status.total_length * 100:.2f}%",
                                    )
                                )

                        # Update finished chunks
                        async with chunk_status.finished_chunks_lock:
                            chunk_status.finished_chunks += 1
                            if chunk_status.finished_chunks == chunk_status.num_chunks:
                                await self.progress_queue.put(
                                    (
                                        download_name,
                                        DownloadStatus.COMPLETED,
                                        "下载完成",
                                    )
                                )
                    return
            except Exception as e:
                chunk_status.retries += 1
                if chunk_status.retries >= self.max_retries:
                    await self.progress_queue.put(
                        (
                            download_name,
                            DownloadStatus.FAILED,
                            f"分块下载失败[ {start} - {end} ]: {str(e)}",
                        )
                    )
                else:
                    await self.progress_queue.put(
                        (
                            download_name,
                            DownloadStatus.RETRYING,
                            f"重试 {chunk_status.retries}/{self.max_retries} 次: {str(e)}",
                        )
                    )
                    await asyncio.sleep(2)  # 等待2秒后重试

    async def _download_single(
        self,
        session: aiohttp.ClientSession,
        url: str,
        file_path: str,
        download_name: str,
        total_length: int,
    ):
        retries = 0
        while retries < self.max_retries:
            try:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(60)
                ) as response:
                    if response.status != 200:  # OK
                        raise Exception(f"Unexpected status code: {response.status}")

                    async with aiofiles.open(file_path, "wb") as f:
                        dl = 0
                        async for data in response.content.iter_chunked(
                            self.iter_chunk_size
                        ):
                            dl += len(data)
                            await f.write(data)
                            done = int(50 * dl / total_length)
                            await self.progress_queue.put(
                                (
                                    download_name,
                                    DownloadStatus.DOWNLOADING,
                                    f"[{'=' * done}{' ' * (50 - done)}] {dl / total_length * 100:.2f}%",
                                )
                            )
                            await self.progress_queue.put(
                                (download_name, DownloadStatus.COMPLETED, "下载完成")
                            )
                    return  # 成功下载后退出循环
            except Exception as e:
                retries += 1
                if retries >= self.max_retries:
                    await self.progress_queue.put(
                        (download_name, DownloadStatus.FAILED, f"下载失败: {str(e)}")
                    )
                else:
                    await self.progress_queue.put(
                        (
                            download_name,
                            DownloadStatus.RETRYING,
                            f"重试 {retries}/{self.max_retries} 次: {str(e)}",
                        )
                    )
                    await asyncio.sleep(2)  # 等待2秒后重试

    async def wait_all_tasks(self):
        await asyncio.gather(*self.downloadTasks)
