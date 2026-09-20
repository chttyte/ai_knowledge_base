from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.process.import_.agent.state import ImportGraphState
from app.rag.import_.config import CHUNK_MAX_SIZE, CHUNK_SIZE
from app.shared.runtime.logger import logger, step_log

def _merge_short_sections(
    section: list[dict],
    min_length: int = CHUNK_SIZE,
    max_length: int = CHUNK_MAX_SIZE,
)-> list[dict]:

    return None


def _split_long_section(
    section: dict,
    max_length: int = CHUNK_MAX_SIZE,
) -> list[dict]:
    """
       内部工具函数：拆分【过长的文本块】，保证单个chunk不超过最大长度限制
       核心逻辑：
        取出 content，没超长就返回 [section]。
        分离标题和正文，计算正文可用长度。
        调用分割器切正文。
        给每块补上标题、来源和序号，返回列表。
       :param section: 待拆分的切块（包含title、content等）
       :param max_length: 单个块最大字符长度
       :return: 拆分后的子块列表
    """
    # 取出 content
    content = section.get("content", "") or ""

    # 没超长就返回 [section]
    if len(content) <= max_length:
        return [section]

    # 统一换行符格式，避免不同系统换行符导致拆分异常
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    # 分离标题和正文, 计算正文可用长度
    title = section.get("title", "") or ""
    # 拼接标题前缀（标题+换行），这部分会占用长度，需要预留空间
    prefix = f"{title}\n\n" if title else ""
    available_len = max_length - len(title)

    # 如果预留后正文无可用长度，直接返回原块，不拆分
    if available_len <= 0:
        return [section]

    body = content
    if title and body.lstrip().startswith(title):
        body = body[len(title) :].lstrip()

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=available_len,  # 拆分后的正文最大长度
        chunk_overlap=0,  # 块之间无重叠
        separators=["\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " "],
    )

    sub_sections = []

    for idx, chunk in enumerate(splitter.split_text(body), start=1):
        text = chunk.lstrip()
        if not text:
            continue

        # 拼接完整内容：标题 + 拆分后的正文
        full_text = (prefix + text).strip()

        sub_sections.append({
            "title": f"{title}-{idx}" if title else f"chunk-{idx}",
            "content": full_text,
            "parent_title":title,
            "part":idx,
            "file_title": section.get("file_title", ""),
        })
    return sub_sections




@step_log("split_by_titles")
def split_by_titles(md_content:str, file_title:str) -> list[dict]:
    """
        按 Markdown 标题（#、##、###...）进行【语义化文档切块】
        特点：
            1. 自动识别标题，保证段落语义完整
            2. 跳过代码块内部的内容，不把 ``` 内的内容误判为标题
            3. 每个块包含：内容、当前标题、文档标题，方便后续检索
        :param md_content: Markdown 文本内容
        :param file_title: 文档名称（用于溯源）
        :return: 切块列表，每个元素是 {content, title, file_title}
        """
    # 正则：匹配 Markdown 标题（# ~ ###### 开头的行）
    import re
    reg = re.compile(r"^\s*#{1,6}\s.+")
    # 将全文按换行符切割成逐行处理
    lines = md_content.split("\n")

    # 存储最终切块结果
    chunks : list[dict] = []

    # 当前正在拼接的块标题
    current_title = None

    # 当前块的所有行内容
    current_title_lines: list[str] = []

    # 标记：是否处于代码块（```...```）内部
    is_code_block = False

    # 记录切块数量
    chunk_size = 0

    # 逐行遍历 MD 内容
    for raw_line in lines:
        line = raw_line.strip()

        if not line:
            logger.warning("空行，跳过本次处理！")
            continue

        # ===================== 代码块判断 =====================
        # 遇到 ``` 或 ~~~ 标记，切换代码块状态
        if line.startswith("```") or line.startswith("~~~"):
            is_code_block = not is_code_block
            current_title_lines.append(line)
            continue

        # ===================== 识别标题并切分 =====================
        # 如果当前行是标题，并且**不在代码块内**，才进行切分
        if reg.match(line) and not is_code_block:
            # 如果已有上一个块内容，就把上一个块保存
            if current_title and len(current_title_lines) > 1:
                chunks.append({
                    "content": "\n".join(current_title_lines),  # 块内容
                    "title": current_title,  # 块标题
                    "file_title": file_title  # 文档名（溯源用）
                })

            # 以当前行作为新块的标题
            current_title = line
            current_title_lines = [current_title]
            chunk_size += 1
        else:
            current_title_lines.append(line)

    # ===================== 保存最后一个块 =====================
    if current_title:
        chunks.append({
            "content": "\n".join(current_title_lines),
            "title": current_title,
            "file_title": file_title
        })
    # ===================== 兜底：全文无标题时 =====================
    if chunk_size == 0:
        chunks.append({
            "content": md_content,
            "title": "default",
            "file_title": file_title
        })
    return chunks



@step_log("load_markdown_content")
def load_markdown_content(state: dict) -> tuple[str, str]:
    """
        从状态字典中安全加载 Markdown 内容和文档标题
        1. 优先从 state 中直接读取
        2. 缺失时自动从文件读取兜底
        3. 统一换行符格式，保证文本干净
        :return: (处理后的md内容, 文件标题)
        """
    # 从状态中获取核心数据：md内容，文件标题，md文件路径
    md_content = state.get("md_content", "")
    file_title = state.get("file_title", "")
    md_path = state.get("md_path", "")

    # ===================== 处理 md_content 缺失场景 =====================
    # 如果状态中没有md内容，尝试从本地md文件读取（兜底逻辑）
    if not md_content:
        logger.warning("没有从state读取到md_content内容,我们使用md_path尝试再次读取!")
        # 如果文件路径存在，则读取文件内容
        if md_path:
            md_content = md_path.read_text(encoding="utf-8")
            state["md_content"] = md_content

        # 双重校验：仍然无内容，抛出异常，终止流程
        if not md_content:
            raise ValueError("md_content无数据，尝试读取md_path依旧为空，终止流程！")

    # ===================== 处理 file_title 缺失场景 =====================
    # 如果标题为空，使用文件名（无后缀）作为标题；无路径则使用默认值
    if not file_title:
        file_title = Path(md_path).stem if md_path else "default"
        state["file_title"] = file_title

    # ===================== 统一文本格式 =====================
    # 替换所有换行符为 \n，解决 Windows/Linux 换行符不一致问题
    md_content = md_content.replace("\r\n", "\n").replace("\r", "\n")

    return md_content, file_title


@step_log("split_document")
def split_document(state: ImportGraphState) -> ImportGraphState:
    """
    文档切分服务：
    1. 按标题层级做一级粗切
    2. 对超长文本做二次细切
    3. 构造 chunks 列表
    4. 回写 chunks
    """

    """
        文档切块核心节点（RAG 最关键步骤）
        功能：加载增强后的 Markdown 内容 → 按标题智能切块 → 优化块大小 → 备份切块结果 → 写入状态
        输出：将分块后的文本列表存入 state，供后续向量化、入库使用
        """
    # 1. 从状态中加载【增强后的Markdown内容】和【文档标题】
    md_content, file_title = load_markdown_content(state)


    return state