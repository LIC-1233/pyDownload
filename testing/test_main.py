import os
import pytest
from src.pyDownload.pyDownload import downloadManager
import logging

logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_main(test_dir: str):
    dm = downloadManager(10, chunk_size=1 * 1024 * 1024)  # 设置分块大小为 1MB
    logger.info(dm.maxTasks)

    await dm.create_download(
        "http://speedtest.tele2.net/10MB.zip",
        os.path.join(test_dir, "10MB1.zip"),
    )
    await dm.create_download(
        "http://speedtest.tele2.net/10MB.zip",
        os.path.join(test_dir, "10MB2.zip"),
    )
    await dm.create_download(
        "http://speedtest.tele2.net/10MB.zip",
        os.path.join(test_dir, "10MB3.zip"),
    )

    # while not all([task.done() for task in dm.downloadTasks]):
    #     logger.info([task.done() for task in dm.downloadTasks])
    #     for dict_name, (status, message) in dm.downloadStatus.items():
    #         logger.info(f"{dict_name}: {status.value} - {message}")
    #     await asyncio.sleep(0.5)

    await dm.wait_all_tasks()
