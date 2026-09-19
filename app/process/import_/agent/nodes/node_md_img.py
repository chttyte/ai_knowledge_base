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
    from pathlib import Path

    d = Path("output/迷你测试")
    if d.exists():
        shutil.rmtree(d)                      # 每次跑都干净
    (d / "images").mkdir(parents=True)

    (d / "手册.md").write_text(
"""# 测试文档

装纸前请注意：

![旧说明](images/ac26d5ab3a9f599eb2f58c2f2cb89f009fd2172b49782804756ea10c7256d4b4.jpg)

再看一眼：

![](images/ac26d5ab3a9f599eb2f58c2f2cb89f009fd2172b49782804756ea10c7256d4b4.jpg)
""", encoding="utf-8")

    # 从讲师输出目录【复制】一张真图过来（只读，不动那边的东西）
    src = Path("D:/BaiduNetdiskDownload/掌柜智库/掌柜智库项目/代码/ai_0119_rag/output/"
               "20260509/282df3a5-870c-4ccc-b282-8fb8dd77763d/hak180产品安全手册/images/"
               "ac26d5ab3a9f599eb2f58c2f2cb89f009fd2172b49782804756ea10c7256d4b4.jpg")
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