"""
应用主包 / 工具模块中的 path_util 模块，负责承载对应场景的具体实现逻辑。
"""
# app/shared/utils/path_util.py
import os
from pathlib import Path

from dotenv import load_dotenv

def get_path_dir(ps:int = 0)->Path:
    """
    pathlib.Path 提供了 parents 属性，这是一个有序的路径上级目录迭代器，直接通过索引取值就能快速获取「上 N 级目录」，完美解决多层 .parent 繁琐的问题，这也是官方推荐的简化写法！
    核心规则：parents[N] 索引对应「向上的层级数」
    parents[0] → 等价于 .parent（当前路径的上 1 级目录）
    parents[1] → 等价于 .parent.parent（当前路径的上 2 级目录）
    parents[2] → 等价于 .parent.parent.parent（当前路径的上 3 级目录）
    以此类推，parents[N] → 直接获取上 N+1 级目录，索引越⼤，层级越靠上
    :param ps:
    :return:
    """
    dir_path = Path(__file__).parents[ps]
    return dir_path


def get_project_root(identifier: str = "pyproject.toml") -> Path:
    """返回项目根目录，允许通过 PROJECT_ROOT 环境变量覆盖。"""
    env_root = os.getenv("PROJECT_ROOT")
    if env_root:
        configured_root = Path(env_root).expanduser().resolve()
        if configured_root.is_dir():
            return configured_root

    start_dir = Path(__file__).resolve().parent
    for current_dir in (start_dir, *start_dir.parents):
        if (current_dir / identifier).is_file():
            load_dotenv(dotenv_path=current_dir / ".env")
            return current_dir

    raise FileNotFoundError(
        f"未找到项目根目录标识「{identifier}」，且环境变量 PROJECT_ROOT 未配置"
    )


PROJECT_ROOT = get_project_root()
