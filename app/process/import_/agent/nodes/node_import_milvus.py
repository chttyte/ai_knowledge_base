from app.shared.runtime.logger import node_log, logger
from app.shared.utils.task_utils import add_done_task, add_running_task
from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.index_service import index_chunks

@node_log("node_import_milvus")
def node_import_milvus(state: ImportGraphState) -> ImportGraphState:
    """
    节点: 导入向量库 (node_import_milvus)
    为什么叫这个名字: 将处理好的向量数据写入 Milvus 数据库。
    """
    add_running_task(state["task_id"], "node_import_milvus")
    state = index_chunks(state)
    add_done_task(state["task_id"], "node_import_milvus")
    return state


if __name__ == '__main__':
    # --- 节点测试 ---
    # 验证链路：建集合 → 按 item_name 清旧数据 → 插入 → 能查回来
    from app.infra.vectorstore.milvus_gateway import milvus_gateway
    from app.rag.import_.config import MILVUS_VECTOR_DIM

    # .env 不用手动加载：上面 import logger 时已经 load_dotenv() 过了

    TEST_ITEM = "测试项目_Milvus"       # 测试数据统一用这一个 item_name
    DIM = MILVUS_VECTOR_DIM
    collection = milvus_gateway.chunks_collection
    client = milvus_gateway.client()

    def make_chunk(n: int, dense_value: float) -> dict:
        """照真实切片的字段造一条测试数据"""
        return {
            "content": f"Milvus 测试文本 {n}",
            "title": f"测试标题{n}",
            # 必须和 state 里的 item_name 完全一致，否则 remove_old_chunks 永远删不掉它
            "item_name": TEST_ITEM,
            "parent_title": f"test{n}.pdf",
            "part": n,
            "file_title": f"test{n}.pdf",
            "dense_vector": [dense_value] * DIM,   # 两条给不同值，才分得清命中哪一条
            "sparse_vector": {1: 0.5, 10: 0.8},
        }

    test_state = {
        "task_id": "test_milvus_task",
        "item_name": TEST_ITEM,
        "chunks": [make_chunk(1, 0.1), make_chunk(2, 0.2)],
    }

    print("正在执行 Milvus 导入节点测试...")
    try:
        node_import_milvus(test_state)

        # 查回来验证，而不是只看日志打印
        rows = client.query(
            collection_name=collection,
            filter=f"item_name == '{TEST_ITEM}'",
            output_fields=["file_title", "content", "part"],
            consistency_level="Strong",   # 刚写完立刻查，不指定可能读不到
        )
        print(f"入库后查到 {len(rows)} 条:")
        for r in rows:
            print(f"  {r}")
        assert len(rows) == 2, f"期望 2 条, 实际 {len(rows)} 条"
        print("✅ 测试通过")
    except Exception as e:
        print(f"❌ 测试失败: {type(e).__name__}: {e}")
    finally:
        # 无论成败都清掉测试数据，别让它留在库里污染真实检索
        client.delete(collection_name=collection, filter=f"item_name == '{TEST_ITEM}'")
        left = client.query(collection_name=collection, filter=f"item_name == '{TEST_ITEM}'",
                            output_fields=["item_name"], consistency_level="Strong")
        print(f"清理完成，测试数据剩 {len(left)} 条")