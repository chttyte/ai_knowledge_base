import shutil
from os import PathLike
from urllib import request

import requests
import time

from langchain_community.embeddings import TitanTakeoffEmbed
from s3transfer import download
from torchvision.datasets.utils import download_and_extract_archive

from app.process.import_.agent.state import ImportGraphState
from pathlib import Path

from app.rag.import_.config import PDF_PARSE_SERVICE_LOCAL_DIR, MINERU_MODEL_VERSION, MINERU_POLL_TIMEOUT_SECONDS, \
    MINERU_POLL_INTERVAL_SECONDS
from app.shared.runtime.logger import logger, PROJECT_ROOT
from app.infra.config.providers import infra_config


def validate_pdf_paths(state: ImportGraphState) -> tuple[Path, Path]:
    # 1.1 state获取pdf_path和local_dir
    pdf_path = state.get("pdf_path")
    local_dir = state.get("local_dir")
    # 1.2 进行pdf_path非空校验
    if not pdf_path:
        logger.error(f"pdf_path参数为空，业务无法继续进行，提前终止！")
        raise ValueError(f"pdf_path参数为空，业务无法继续进行，提前终止！")
    # 1.3 进行local_path的非空校验
    if not local_dir:
        logger.warning(f"local_dir为空，赋值默认值，默认为：项目根地址/output 文件夹")
        local_dir:Path = PROJECT_ROOT / PDF_PARSE_SERVICE_LOCAL_DIR
        state["local_dir"] = str(local_dir)

    # 1.4 将pdf_path和local_dir转成Path
    pdf_path_obj:Path = Path(pdf_path)
    local_dir_obj:Path = Path(local_dir)
    # 1.5 pdf_path_obj 判断是否存在
    if not pdf_path_obj.exists():
        logger.error(f"存在pdf_path地址：{str(pdf_path_obj)}, 但是地址没有对应文件，业务无法继续进行，提前终止！")
        raise FileNotFoundError(f"存在pdf_path地址：{str(pdf_path_obj)}, 但是地址没有对应文件，业务无法继续进行，提前终止！")
    # 1.6 local_dir_obj是不是目录
    if not local_dir_obj.is_dir():
        logger.warning(f"存在local_dir:{str(local_dir_obj)}, 但是没有对应文件夹，创建对应文件夹，业务继续！")
        local_dir_obj.mkdir(parents=True, exist_ok=True)
    # 1.7 返回结果：pdf_path_obj, local_dir_obj
    return pdf_path_obj, local_dir_obj

def upload_pdf_and_poll(pdf_path_obj: Path) -> str:
    header = {
        "Content-Type": "application/json",
        # .env配置文件 -> infra /config / providers / minerU
        "Authorization": f"Bearer {infra_config.mineru_config.api_key}"
    }
    data = {
        "files": [
            {"name": f"{pdf_path_obj.name}"}
        ],

        "model_version": MINERU_MODEL_VERSION
    }
    url = f"{infra_config.mineru_config.base_url}/file-urls/batch"
    # json请求体参数  data传请求体字节数据
    response =  requests.post(url=url, headers=header, json=data)
    # 所有网络请求，必须两步骤判断 1.状态码 200 2. 业务必须成功
    if response.status_code != 200:
        logger.error(f"向minerU服务器申请上传文件解析，但是状态码为：{response.status_code}，转态错误，业务无法继续！")
        raise  RuntimeError(f"向minerU服务器申请上传文件解析，但是状态码为：{response.status_code}，转态错误，业务无法继续！")
    # 拿到响应体，解析成字典
    response_dict = response.json()
    if response_dict.get('code', -1) != 0:
        logger.error(f"向minerU服务器申请上传文件解析，网络状态正常，服务业务状态异常，code={response_dict.get('code', -1)},"
                     f"错误原因：{response_dict.get('msg')}，无法继续业务！")
        raise RuntimeError(f"向minerU服务器申请上传文件解析，网络状态正常，服务业务状态异常，code={response_dict.get('code', -1)},"
                     f"错误原因：{response_dict.get('msg')}，无法继续业务！")

    # 网络没问题/业务也没问题
    batch_id = response_dict.get('data', {}).get('batch_id')
    file_upload_urls = response_dict.get('data', {}).get('file_urls', [])
    file_upload_url = None
    if len(file_upload_urls) > 0:
        file_upload_url = file_upload_urls[0]

    if not batch_id:
        logger.error(f"申请minerU解析文件，返回batch_id为空，业务中断！")
        raise ValueError(f"申请minerU解析文件，返回batch_id为空，业务中断！")

    logger.info(f"完成文件上传申请，batch_id:{batch_id}, 文件上传预签名地址：{file_upload_url}")
    # 2.2 向指定的url地址发起请求并上传pdf文件
    # 预签名地址：尽量让请求干净，不要携带其他不相关的代理头
    with requests.Session() as session:
        session.trust_env = False
        upload_response =  session.put(url=file_upload_url, data=pdf_path_obj.read_bytes())
        # 判断业务状态码 code==0，为什么？因为不是一个接口，就是文件服务器特殊的上传地址，只有网络状态码，没有业务
    if upload_response.status_code != 200:
        logger.error(f"向{file_upload_url}上传文件，"
                    f"服务器返回的网络状态码为{upload_response.status_code}，业务失败提前终止！")
        raise RuntimeError(f"向{file_upload_url}上传文件，"
                        f"服务器返回的网络状态码为{upload_response.status_code}，业务失败提前终止！")

    # 2.3 轮询向minerU获取batch_id解析状态 zip_url
    # 方案1：回调（minerU -> 我们服务器的fastapi）
    # 方案2：轮询
    result_url = f"{infra_config.mineru_config.base_url}/extract-results/batch/{batch_id}"
    # 3种场景
    start_time = time.time()
    while True:
        # 1.先判断时间是否超时
        if time.time() - start_time >= MINERU_POLL_TIMEOUT_SECONDS:
            logger.warning(f"轮询获取{batch_id}对应的解析结果超时！耗时为：{time.time()-start_time}")
            raise TimeoutError(f"轮询获取{batch_id}对应的解析结果超时！耗时为：{time.time()-start_time}")
        # 2. 没有超时向接口发起请求获取解析结果
        try:
            poll_result = requests.get(url=result_url, headers=header)
        except Exception as e:
            logger.warning(f"申请结果出现网络波动{str(e)}, 稍后再试！")
            time.sleep(MINERU_POLL_INTERVAL_SECONDS)
            continue
        # 3. 网络状态判定
        if poll_result.status_code != 200:
            # 服务器端错误，给机会重试
            if 500 <= poll_result.status_code < 600:
                logger.warning(f"申请结果出现网络状态错误：{poll_result.status_code}, 稍后再试！")
                time.sleep(MINERU_POLL_INTERVAL_SECONDS)
                continue
            else:
                logger.error(f"获取：{batch_id}对应解析结果，服务器访问报错，http状态码：{poll_result.status_code}"
                             f"错误无法修复，业务失败，提前终止！")
                raise RuntimeError(f"获取：{batch_id}对应解析结果，服务器访问报错，http状态码：{poll_result.status_code}"
                             f"错误无法修复，业务失败，提前终止！")
        # 4. 业务状态判断
        poll_result_dict = poll_result.json()
        if poll_result_dict.get('code', -1) != 0:
            # 业务失败，不拯救
            logger.error(f"获取：{batch_id}对应解析结果，业务状态报错，业务状态码：{poll_result_dict.get('code', -1)}"
                         f"错误信息{poll_result_dict.get('msg')}，业务失败，提前终止！")
            raise RuntimeError(f"获取：{batch_id}对应解析结果，业务状态报错，业务状态码：{poll_result_dict.get('code', -1)}"
                         f"错误信息{poll_result_dict.get('msg')}，业务失败，提前终止！")
        # 5. 获取解析结果和状态判定
        extract_result_list = poll_result_dict.get('data', {}).get('extract_result', [])
        if len(extract_result_list) == 0:
            logger.warning(f"解析结果extract_result_list为空，跳过本次，稍后再试！")
            time.sleep(MINERU_POLL_INTERVAL_SECONDS)
            continue
        extract_result = extract_result_list[0]
        state = extract_result.get('state')
        if state == 'done':
            # 解析完毕，成功
            full_zip_url = extract_result.get('full_zip_url')
            if not full_zip_url:
                # 不给机会
                logger.error(f"{batch_id}对应的解析已经完成，但full_zip_url没有地址！业务失败！")
                raise ValueError(f"{batch_id}对应的解析已经完成，但full_zip_url没有地址！业务失败！")
            return full_zip_url
        elif state == 'failed':
            # 解析完毕，失败
            logger.error(f"{batch_id}对应的解析已经完成，但解析失败！业务失败！")
            raise ValueError(f"{batch_id}对应的解析已经完成，但解析失败！业务失败！")
        else:
            logger.warning(f"本次解析，没有获得结果，继续下一次！")
            time.sleep(MINERU_POLL_INTERVAL_SECONDS)
            continue


def download_and_extract_markdown(zip_url:str, local_dir_obj:Path , file_name:str) -> Path:
    """
        进行地址下载和解压，以及重命名，最终返回md_path_obj
    :param zip_url:
    :param local_dir_obj:
    :param file_name:
    :return:
    """
    # 1. 下载（3次重试）
    response = requests.get(url=zip_url, timeout=MINERU_POLL_TIMEOUT_SECONDS)
    # 文件服务器，只需检查status_code
    if response.status_code != 200:
        logger.error(f"向指定地址：{zip_url}下载zip文件报错，状态码：{response.status_code}"
                     f"业务无法继续进行！")
    #准备zip文件对象
    zip_path_obj:Path = local_dir_obj / f"{file_name}.zip"
    """
        response
            .status_code
            .json()  服务器返回的json字符串 -> dict
            .text    服务器返回的json字符串 -> str -> json.loads
            .content 服务器返回的字节数据
    """
    zip_path_obj.write_bytes(response.content)
    # 2. 解压
    # 创建一个解压后的文件夹 output / 文件名
    zip_extract_dir:Path = local_dir_obj / file_name
    if zip_extract_dir.is_dir():
        # 解压过，清空，避免脏数据'
        # shutil.rmtree -> 递归清空 清空文件夹和文件本身
        shutil.rmtree(zip_extract_dir)
        zip_extract_dir.mkdir(parents=True, exist_ok=True)
        # 解压
        # unpack_archive 支持所有格式的压缩包
    shutil.unpack_archive(zip_path_obj, zip_extract_dir)
    # 3. 重命名
    # 找到文件夹的指定类型.md
    md_obj_list: list[Path] = list(zip_extract_dir.rglob("*.md")) # 递归搜索
    if len(md_obj_list) == 0:
        logger.error(f"解压后发现没有md文件，业务无法继续进行！")
        raise ValueError(f"解压后发现没有md文件，业务无法继续进行！")
    # 情况1：就是文件名 -> return
    for current_md_obj in md_obj_list:
        if current_md_obj.stem == file_name:
            logger.info(f"解压后的文件名，等于原文件名{file_name}，直接返回！")
            return current_md_obj
    # 情况2：full ->记录
    md_obj_path: Path = None
    for current_md_obj in md_obj_list:
        if current_md_obj.stem == 'full':
            md_obj_path = current_md_obj
            break
    # 情况3：xxx -> 记录
    if not md_obj_path:
        md_obj_path = md_obj_list[0]
    logger.info(f"触发了md文件的重命名机制，原名称：{md_obj_path.stem}, 目标名称：{file_name}")
    # md_obj_path.rename(f"{file_name}.md")
    md_obj_path = md_obj_path.rename(md_obj_path.with_name(f"{file_name}.md"))
    return md_obj_path



def parse_pdf_to_markdown(state: ImportGraphState) -> ImportGraphState:
    """
    PDF 解析服务：
    1. 调用 MinerU
    2. 下载并解压解析结果
    3. 获取 Markdown 路径和正文内容
    4. 回写 md_path / md_content / local_dir
    """
    # 1. 校验文件名/目录参数，返回tuple(pdf_path_obj, local_dir_obj)
    pdf_path_obj, local_dir_obj = validate_pdf_paths(state)
    # 2. minerU解析pdf文件并返回zip的下载地址
    zip_url: str = upload_pdf_and_poll(pdf_path_obj)
    # 3. 根据zip_url下载并解压md文件
    md_path_obj: Path = download_and_extract_markdown(zip_url, local_dir_obj, pdf_path_obj.stem)
    state['md_path'] = str(md_path_obj)
    state['md_content'] = md_path_obj.read_text()
    state['local_dir'] = str(local_dir_obj)
    return state