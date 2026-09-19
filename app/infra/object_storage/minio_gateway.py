from minio import Minio
from app.shared.clients.minio_utils import get_minio_client
from app.infra.config.providers import infra_config

# 引入现有的功能， 进行汇总

class MinIOGateway:
    # 提供获取桶名称的函数
    @property
    def bucket_name(self):
        return infra_config.minio.bucket_name

    # 提供获取图片前缀的函数
    @property
    def image_dir(self):
        return infra_config.minio.minio_img_dir

    # 提供获取minio_client的函数
    @property
    def client(self):
        return get_minio_client()

    # minio上传文件不会返回访问地址，拼接访问地址 http/https 端点 桶 对象名
    def build_image_url(self, stem: str, image_name: str) -> str:
        """
        拼接生成 MinIO 图片的可访问URL（HTTP/HTTPS）
        :param stem: 文档名称（不带后缀），用于区分不同文档的图片
        :param image_name: 图片原始文件名
        :return: 可直接访问的 MinIO 图片完整URL
        """
        # 根据配置决定使用 http 还是 https
        protocol = "https" if infra_config.minio.minio_secure else "http"

        # 拼接最终可访问的图片在线地址
        return (
            f"{protocol}://{infra_config.minio.endpoint}/"
            f"{self.bucket_name}{self.image_dir}/{stem}/{image_name}"
        )

minio_gateway = MinIOGateway()

