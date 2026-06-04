"""兼容 `python -m SKILLS.src` 的命令行入口。"""

from ..cli import main

if __name__ == "__main__":
    raise SystemExit(main())
