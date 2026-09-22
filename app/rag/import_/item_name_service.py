from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from pymilvus import MilvusClient, DataType

from app.infra.llm.providers import llm_provider
from app.infra.vectorstore.milvus_gateway import milvus_gateway
from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.config import ITEM_NAME_CONTEXT_CHUNK_K, ITEM_NAME_CONTEXT_TOTAL_MAX_CHARS, \
    MILVUS_DEFAULT_VARCHAR_MAX_LENGTH, MILVUS_VECTOR_DIM
from app.shared.runtime.load_prompt import load_prompt
from app.shared.runtime.logger import step_log, logger
from app.shared.utils.escape_milvus_string_utils import escape_milvus_string


@step_log("upsert_item_name")
def upsert_item_name(
    item_name: str,
    file_title: str,
    dense_vector: list[float],
    sparse_vector: dict[int, float],
) -> None:
    """
       将主体名称及向量写入 Milvus 集合（先删后插，保证幂等性）
       功能：确保同一个 item_name 在集合中只有一条最新记录
       :param item_name: 主体名称
       :param file_title: 文件标题
       :param dense_vector: 稠密向量列表
       :param sparse_vector: 稀疏向量字典
       :return: 无返回值
    """
    # 获取 Milvus 客户端
    milvus_client = milvus_gateway.client()

    # 确保集合已创建
    prepare_item_name_collection()


    # 对 item_name 进行转义处理，防止特殊字符导致注入攻击
    safe_item_name = escape_milvus_string(item_name)

    # ===================== 删除已有记录 =====================
    # 先删除已存在的相同 item_name 记录，保证幂等性
    milvus_client.delete(
        collection_name=milvus_gateway.item_name_collection,
        filter=f"item_name == '{safe_item_name}'",
    )

    # ===================== 插入新记录 =====================
    # 插入包含完整信息的新记录
    milvus_client.insert(
        collection_name=milvus_gateway.item_name_collection,
        data=[
            {
                "file_title": file_title,
                "item_name": item_name,
                "dense_vector": dense_vector,
                "sparse_vector": sparse_vector,
            }
        ],
    )


@step_log("prepare_item_name_collection")
def prepare_item_name_collection()->None:
    """
       准备 Milvus 主体名称集合
       功能：检查集合是否存在，不存在则创建 schema 和索引
       :return: 无返回值
    """
    # 获取 Milvus 客户端
    milvus_client = milvus_gateway.client()

    # 获取集合名称（从配置中读取）
    collection_name = milvus_gateway.item_name_collection

    # 如果集合已存在，直接返回，无需重复创建
    if milvus_client.has_collection(collection_name):
        return

    # ===================== 创建 Schema =====================
    # 创建 schema，启用自动 ID 和动态字段
    schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=True)

    # 添加主键字段：pk，INT64 类型，自增
    schema.add_field(field_name='pk', datatype=DataType.INT64,
                     is_primary=True,
                     auto_id=True)
    schema.add_field(field_name='file_title', datatype=DataType.VARCHAR,
                     max_length=MILVUS_DEFAULT_VARCHAR_MAX_LENGTH)
    schema.add_field(field_name='item_name', datatype=DataType.VARCHAR,
                     max_length=MILVUS_DEFAULT_VARCHAR_MAX_LENGTH)
    schema.add_field(field_name='dense_vector', datatype=DataType.FLOAT_VECTOR, dim=MILVUS_VECTOR_DIM)
    schema.add_field(field_name='sparse_vector', datatype=DataType.SPARSE_FLOAT_VECTOR)

    # ===================== 创建索引 =====================
    # 准备索引参数
    index_params = milvus_client.prepare_index_params()

    # 为稠密向量创建索引：使用 autoindex，metric_type 为 IP（内积）
    index_params.add_index(
        field_name='dense_vector',
        index_type="AUTOINDEX",
        index_name="dense_vector_index",
        metric_type="IP",
    )

    # 为稀疏向量创建索引：使用 SPARSE_INVERTED_INDEX，算法为 DAAT_MAXSCORE
    index_params.add_index(
        field_name='sparse_vector',
        index_type="SPARSE_INVERTED_INDEX",
        index_name="sparse_vector_index",
        metric_type="IP",
        params={"inverted_index_algo": "DAAT_MAXSCORE"},
    )

    milvus_client.create_collection(collection_name=collection_name,
                                    schema=schema,
                                    index_params=index_params)



@step_log("embed_item_name")
def embed_item_name(item_name:str) -> tuple[list[float], dict[int, float]]:
    result = llm_provider.embed_document([item_name])
    # 提取第一个（也是唯一一个）文本的稠密向量和稀疏向量
    # dense: list[float] - 长度为 1024 的浮点数列表
    # sparse: dict[int, float] - {特征索引: 权重} 的字典
    return result["dense"][0], result["sparse"][0]

@step_log("apply_item_name")
def apply_item_name(chunks: list[dict], item_name: str) -> list[dict]:
    """
       将识别出的主体名称回填到所有切片中
       功能：为每个切片添加 item_name 字段，建立切片与主体的关联关系
       :param chunks: 文档切片列表
       :param item_name: 识别出的主体名称
       :return: 更新后的切片列表
    """

    for chunk in chunks:
        chunk["item_name"] = item_name

    return chunks


@step_log("recognize_item_name")
def recognize_item_name(context: str, file_title: str) -> str:
    """
        调用大语言模型识别文档主体名称
        功能：基于文档上下文和提示词，让 LLM 输出当前文档对应的核心产品名
        :param context: 由前 K 个切片拼接的上下文字符串
        :param file_title: 文件标题，用于兜底
        :return: 识别出的主体名称，如果识别失败则返回 file_title
    """
    # 获取 LLM 客户端（从 llm_provider 中获取）
    llm = llm_provider.chat()

    # 加载系统提示词模板
    system_prompt_str = load_prompt("product_recognition_system")

    # 加载用户提示词模板，传入 file_title 和 context
    user_prompt_str = load_prompt("item_name_recognition",
                                  file_title=file_title,
                                  context=context)
    messages = [
        SystemMessage(content=system_prompt_str),
        HumanMessage(content=user_prompt_str),
    ]

    item_name = (llm | StrOutputParser()).invoke(messages)
    return item_name or file_title

@step_log("build_document_context")
def build_document_context(chunks: list[dict]) -> str:
    """
       从前 K 个切片中构建用于 LLM 识别的上下文字符串
       功能：提取文档头部高价值信息，控制上下文长度，降低推理成本
       :param chunks: 文档切片列表，每个元素包含 title、content 等字段
       :return: 拼接后的上下文字符串，已做长度截断
    """
    # 截取前 K 个切片（由配置 ITEM_NAME_CONTEXT_CHUNK_K 控制）
    current_chunks = chunks[:ITEM_NAME_CONTEXT_CHUNK_K]

    # 存储格式化后的切片字符串
    chunks_str_list:list[str] = []

    # 遍历切片，拼接格式化字符串
    for index, item in enumerate(current_chunks, start=1):
        chunks_str_list.append(f"切片:{index}，标题:{item['title']}，内容：:{item['content']}")

    # 用换行符连接所有切片
    chunk_str = "\n".join(chunks_str_list)

    # 截断到最大字符数限制（由配置 ITEM_NAME_CONTEXT_TOTAL_MAX_CHARS 控制）
    return chunk_str[:ITEM_NAME_CONTEXT_TOTAL_MAX_CHARS]


@step_log("validate_chunks_and_title")
def validate_chunks_and_title(state: dict) -> tuple[list[dict], str]:
    """
       校验并提取 state 中的 chunks 和 file_title
       功能：确保后续流程有有效的输入数据，缺失时提供兜底策略
       :param state: LangGraph 流程状态字典
       :return: (chunks列表, file_title字符串)
    """
    chunks = state.get('chunks', [])
    file_title = state.get('file_title')

    # ===================== 校验 chunks =====================
    # 如果 chunks 为空，无法继续业务，直接抛出异常终止流程
    if not chunks:
        logger.error("chunks没有内容,无法继续业务!")
        raise ValueError("chunks没有内容,无法继续业务!")

    # ===================== 处理 file_title 缺失场景 =====================
    # 如果标题为空，使用默认值兜底，避免后续流程出错
    if not file_title:
        logger.warning("file_title为空给与默认值处理!")
        file_title = "default_title"
        state["file_title"] = file_title  # 回填到 state

    return chunks, file_title


def recognize_and_index_item_name(state: ImportGraphState) -> ImportGraphState:
    """
    主体识别服务：
    1. 基于 chunks 构造上下文
    2. 调用 LLM 识别 item_name
    3. 将 item_name 回填到 state 和 chunks
    4. 同步写入主体名称索引
    """
    chunks, file_title = validate_chunks_and_title(state)
    context = build_document_context(chunks)
    item_name = recognize_item_name(context, file_title)

    state["item_name"] = item_name
    state["chunks"] = apply_item_name(chunks, item_name)
    dense_vector, sparse_vector = embed_item_name(item_name)
    upsert_item_name(item_name, file_title, dense_vector, sparse_vector)

    return state
