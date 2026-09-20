from app.shared.runtime.logger import node_log
from app.shared.utils.task_utils import add_done_task, add_running_task
from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.split_service import split_document

@node_log("node_document_split")
def node_document_split(state: ImportGraphState) -> ImportGraphState:
    """
    节点: 文档切分 (node_document_split)
    为什么叫这个名字: 将长文档切分成小的 Chunks (切片) 以便检索。
    """
    add_running_task(state["task_id"], "node_document_split")
    state = split_document(state)
    add_done_task(state["task_id"], "node_document_split")
    return state


if __name__ == "__main__":
    # 手测：拿 测试数据/ 下的三份假数据跑 split_by_titles，看日志和输出
    # 跑法：PYTHONPATH=. .venv/Scripts/python.exe app/process/import_/agent/nodes/node_document_split.py
    # 预期输出见 测试数据/预期结果.md
    from app.shared.runtime.logger import PROJECT_ROOT
    from app.rag.import_.split_service import split_by_titles

    data_dir = PROJECT_ROOT / "app" / "process" / "import_" / "agent" / "nodes" / "测试数据"

    for name in ["切分测试.md", "无标题.md", "围栏没配对.md"]:
        md = (data_dir / name).read_text(encoding="utf-8")
        chunks = split_by_titles(md, name[:-3])
        print(f"\n===== {name} → {len(chunks)} 块 =====")
        for i, c in enumerate(chunks):
            print(f"  [{i}] {c['title']!r}  {c['content'][:60]!r}")
