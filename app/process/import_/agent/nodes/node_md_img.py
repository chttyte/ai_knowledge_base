import os
from app.shared.runtime.logger import node_log, logger
from app.shared.utils.task_utils import add_done_task, add_running_task
from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.enrich_markdown_images import (
    enrich_markdown_images,
    scan_images,
    upload_images_and_replace,
    backup_markdown,
)

@node_log("node_md_img")
def node_md_img(state: ImportGraphState) -> ImportGraphState:
    """
    节点: 图片处理 (node_md_img)
    为什么叫这个名字: 处理 Markdown 中的图片资源 (Image)。
    """
    add_running_task(state["task_id"], "node_md_img")
    state = enrich_markdown_images(state)
    add_done_task(state["task_id"], "node_md_img")
    return state



if __name__ == "__main__":
    import shutil

    from app.shared.utils.path_util import PROJECT_ROOT

    d = PROJECT_ROOT / "output" / "迷你测试"
    if d.exists():
        shutil.rmtree(d)                      # 每次跑都干净
    (d / "images").mkdir(parents=True)

    # 从当前项目输出目录复制一张真图（只读，不修改原文件）
    source_images_dir = PROJECT_ROOT / "output" / "hak180使用说明书" / "images"
    src = next(iter(sorted(source_images_dir.glob("*.jpg"))), None)
    if src is None:
        raise FileNotFoundError(f"测试图片目录中没有 JPG 文件：{source_images_dir}")

    (d / "手册.md").write_text(
f"""# 测试文档

装纸前请注意：

![旧说明](images/{src.name})

再看一眼：

![](images/{src.name})
""", encoding="utf-8")

    shutil.copy(src, d / "images" / src.name)

    # 走完整流程
    state = {
        "task_id": "t1",
        "md_path": str(d / "手册.md"),
        "md_content": "",
    }
    state = enrich_markdown_images(state)

    print("=" * 60)
    print("新的 md_path   :", state["md_path"])
    print("新的 md_content:")
    print(state["md_content"])

