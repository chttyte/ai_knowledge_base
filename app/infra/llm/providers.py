from langchain_openai import ChatOpenAI

from app.infra.config.providers import infra_config
from app.shared.model import generate_embeddings, get_bge_m3_ef, get_llm_client, get_reranker_model

class LLMProvider:
    def chat(self, model: str | None = None, json_mode: bool = False) -> ChatOpenAI:
        """
        获取【普通文本对话】LLM 客户端
        :param model: 可选，指定模型名称，不填则使用默认配置
        :param json_mode: 是否开启 JSON 格式输出模式
        :return: 可直接调用的 LangChain LLM 客户端
        """
        return get_llm_client(model=model, json_mode=json_mode)

    def vision_chat(self) -> ChatOpenAI:
        """
        获取【视觉对话】LLM 客户端（用于图片理解、图片摘要、多模态理解）
        默认使用配置中的 lv_model（视觉大模型）
        :return: 视觉模型客户端
        """
        return get_llm_client(model=infra_config.llm.lv_model)

llm_provider = LLMProvider()