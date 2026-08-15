"""等某个本地服务就绪。给启动.bat 用。

    python 等待就绪.py http://127.0.0.1:8756/api/health 30

不用批处理的 timeout + 轮询，因为：
  1. `timeout` 可能撞上 PATH 里的同名命令（如 Git Bash 自带的）
  2. 批处理里写轮询要一堆 goto，可读性差

就绪返回 0，超时返回 1。
"""

import sys
import time
import urllib.error
import urllib.request


def main():
    if len(sys.argv) < 2:
        print("用法: python 等待就绪.py <url> [超时秒数]")
        return 1
    url = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 30

    t0 = time.time()
    while time.time() - t0 < limit:
        try:
            urllib.request.urlopen(url, timeout=2)
            return 0
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(1)
    return 1


if __name__ == "__main__":
    sys.exit(main())
