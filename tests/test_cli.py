import signal
import subprocess
import sys
import time


def test_cli():
    process = subprocess.Popen(
        [sys.executable, "-m", "shadowproxy2", "-v", "socks5://:0"]
    )
    time.sleep(3)
    process.send_signal(signal.SIGINT)
    process.wait(timeout=3)
    assert process.returncode == 0
