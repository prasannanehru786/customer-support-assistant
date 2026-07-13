from __future__ import annotations

import sys
import urllib.error
import urllib.request


def main() -> int:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8501/_stcore/health", timeout=5) as response:
            return 0 if response.status == 200 else 1
    except (urllib.error.URLError, TimeoutError):
        return 1


if __name__ == "__main__":
    sys.exit(main())

