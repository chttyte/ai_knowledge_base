from app.process.import_.agent.state import ImportGraphState
from app.shared.runtime.logger import logger, step_log
from pathlib import Path

@step_log("import_graph_state")
def resolve_input_file(state: ImportGraphState) -> ImportGraphState:
    """

    :param state: task_id, local_file_path
    :return: md_path, is_md_read_enabled, pdf_path, is_pdf_read_enabled, file title
    """
    # 1.先获取local_file_path参数 state
    local_file_path = state.get("local_file_path")

    # 2.local_file_path进行非空校验->空->直接抛出异常FileNotFound
    if not local_file_path:
        logger.warning("local_file_path not exist")
        raise FileNotFoundError("local_file_path not found!")

    # 3. 判断是不是md
    if local_file_path.endswith(".md"):
        state["md_path"] = local_file_path
        state["is_md_read_enabled"] = True
        state["is_pdf_read_enabled"] = False
    # 4，判断是不是pdf
    elif local_file_path.endswith(".pdf"):
        state["pdf_path"] = local_file_path
        state["is_md_read_enabled"] = False
        state["is_pdf_read_enabled"] = True
    # 扩展文件类型
    # elif
    # 5.都不是做好警告提示 is_md_read_enabled is_pdf_read_enabled = False 提前结束
    else:
        logger.warning(f"{local_file_path}对应的文件类型无法解析，仅支持md/pdf格式类型，提前终止，跳转至END节点！")
        state["is_md_read_enabled"] = False
        state["is_pdf_read_enabled"] = False
        return state
    # 6. 获取file_title参数，同步更新state
    # Path
    file_title = Path(local_file_path).stem
    # 7.返回处理后的state
    state["file_title"] = file_title

    return state