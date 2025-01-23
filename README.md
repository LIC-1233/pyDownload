

# pyDownload

`pyDownload` 是一个用于异步下载文件的 Python 库。它支持分块下载和单线程下载，并且具有重试机制，确保下载的可靠性。

## 特点

- **异步下载**：利用 `aiohttp` 和 `aiofiles` 实现高效的异步下载。
- **分块下载**：支持分块下载，提高下载速度和可靠性。
- **重试机制**：在下载失败时自动重试，确保下载成功。
- **进度监控**：实时监控下载进度，提供详细的日志记录。

## 安装

你可以通过 `pip` 安装 `pyDownload`：

```sh
pip install pydownload
```

或者从源码安装：

```sh
git clone https://github.com/yourusername/pyDownload.git
cd pyDownload
pip install .
```

## 使用方法

### 基本用法

以下是一个简单的示例，演示如何使用 `pyDownload` 进行文件下载。

#### 示例代码

```python
import asyncio
from src.pyDownload.pyDownload import downloadManager

async def main():
    dm = downloadManager(maxTasks=5, chunk_size=4 * 1024 * 1024, max_retries=3)

    await dm.create_download(
        "http://speedtest.tele2.net/10MB.zip",
        "/path/to/test/directory/10MB1.zip",
    )
    await dm.create_download(
        "http://speedtest.tele2.net/10MB.zip",
        "/path/to/test/directory/10MB2.zip",
    )
    await dm.create_download(
        "http://speedtest.tele2.net/10MB.zip",
        "/path/to/test/directory/10MB3.zip",
    )

    # 等待所有任务完成
    await dm.wait_all_tasks()

if __name__ == "__main__":
    asyncio.run(main())


### 使用 `pytest` 进行测试

你可以使用 `pytest` 来运行测试，并指定测试目录。

#### 运行测试

```sh
pytest --test-dir=/path/to/test/directory
```

## 日志配置

`pyDownload` 使用 `logging` 模块进行日志记录。你可以通过配置 `logging` 模块来调整日志级别和输出位置。

#### `pytest.ini`

```ini
[pytest]
addopts = --test-dir=/tmp/pydownload_test

[pytest.ini_options]
log_cli = true
log_cli_level = info
log_date_format = "%Y-%m-%d %H:%M:%S"
log_file = "./testing/log/pytest.log"
log_file_date_format = "%Y-%m-%d %H:%M:%S"
log_file_format = "%(asctime)s %(levelname)s %(message)s"
log_file_level = info
log_file_mode = w+
log_format = "%(asctime)s %(levelname)s %(message)s"
```

## 许可证

本项目采用 MIT 许可证。请查看 [LICENSE](LICENSE) 文件了解更多信息。

