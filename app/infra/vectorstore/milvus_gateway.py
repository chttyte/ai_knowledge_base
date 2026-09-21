from app.infra.config.providers import infra_config
from app.shared.clients import get_milvus_client

class MilvusGateway:
    @property
    def chunk_collection_name(self):
        return infra_config.milvus.chunk_collection_name

    @property
    def item_name_collection(self) -> str:
        return infra_config.milvus.item_name_collection

    def client(self):
        return get_milvus_client()

    # def create(
    #     self,
    #     dense_vector: list[float],
    #     sparse_vector: dict[int , float],
    #     *,
    #     expr:str=None,
    #     limit:int=5,
    # ):


milvus_gateway = MilvusGateway()