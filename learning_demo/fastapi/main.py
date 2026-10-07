import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse, StreamingResponse, Response

from app.shared.config.settings_config import settings

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "Hello World"}


# 访问 http://127.0.0.1:8000/items/5?q=手机
@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    """
    item_id: 路径参数（必填），自动转为 int 类型
    q: 查询参数（可选），默认为 None
    """
    return {"item_id": item_id, "q": q}

class Item(BaseModel):
    name: str  # 必填，字符串类型
    price: float  # 必填，浮点数类型
    description: str | None = None  # 可选，默认为 None

 # POST 请求接收 JSON 数据
@app.post("/items/")
def create_item(item: Item):
    """
            FastAPI 会自动：
            1. 解析请求体中的 JSON 数据
            2. 验证数据类型是否正确
            3. 如果验证失败，返回详细的错误信息
    """
    return {
        "name": item.name,
        "price": item.price,
        "description": item.description
    }


from fastapi import FastAPI, File, UploadFile

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    file: UploadFile 对象，包含以下属性：
      - file.filename: 文件名（如 "document.pdf"）
      - file.content_type: MIME 类型（如 "application/pdf"）
      - file.file: 文件内容（异步文件对象）

    File(...): 表示该参数为必填项
    """
    # 读取文件内容（异步操作，需要用 await）
    content = await file.read()

    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(content)
}


# 定义一个耗时任务（普通函数即可）
def process_data(task_id: str, data: str):
    """
    模拟耗时操作（如处理文件、调用 AI 模型等）
    这个函数会在后台异步执行，不阻塞 HTTP 响应
    """
    print(f"[{task_id}] 开始处理数据: {data}")
    time.sleep(5)  # 模拟耗时 5 秒
    print(f"[{task_id}] 数据处理完成")
    # 可以在这里更新数据库、写入文件等


@app.post("/start-task")
async def start_task(background_tasks: BackgroundTasks):
    """
    background_tasks: FastAPI 提供的后台任务管理器
    add_task(): 将任务加入后台队列
    """
    task_id = "task-001"

    # 将耗时任务加入后台队列
    # 注意：这里只是"注册"任务，不会立即执行
    background_tasks.add_task(process_data, task_id, "测试数据")

    # 立即返回响应，不需要等待 process_data 执行完毕
    return {
        "task_id": task_id,
        "message": "Task started in background"
    }



# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # 允许所有来源（生产环境建议指定具体域名）
    allow_credentials=True,         # 允许携带凭证（如 Cookie）
    allow_methods=["*"],            # 允许所有 HTTP 方法（GET、POST、PUT、DELETE 等）
    allow_headers=["*"],            # 允许所有请求头
)

@app.get("/api/data")
def get_data():
    return {"message": "Hello from backend"}



@app.get("/api/user")
def get_user():
    # 等价于直接 return {"name": "张三", "age": 20}（FastAPI 自动转 JSONResponse）
    return JSONResponse(
        content={"name": "张三", "age": 20},
        status_code=200,  # 可选，默认 200
        headers={"X-Custom-Header": "custom-value"}  # 可选，自定义响应头
    )


@app.get("/download/excel")
def download_excel():
    excel_path = Path(__file__).parent / "data" / "月度报表.xlsx"
    # 返回文件并指定下载文件名
    return FileResponse(
        path=excel_path,
        filename="月度报表.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

@app.get("/hello")
def hello(name: str = "游客"):
    html_content = f"""
    <html>
        <body>
            <h1>你好，{name}！</h1>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content, status_code=200)

@app.get("/old-path")
def redirect_old_path():
    # 重定向到 /new-path，状态码 307 表示临时重定向
    return RedirectResponse(url="/new-path", status_code=307)

@app.get("/new-path")
def new_path():
    return {"message": "这是新接口"}



async def generate_stream():
    # 模拟流式输出（逐字返回）
    words = ["你", "好", "，", "这", "是", "流", "式", "响", "应"]
    for word in words:
        await asyncio.sleep(0.5)
        yield word.encode("utf-8")  # 流式输出需返回字节流

@app.get("/stream")
async def stream_response():
    return StreamingResponse(generate_stream(), media_type="text/event-stream")

@app.get("/custom")
def custom_response():
    # 返回二进制数据，指定自定义 MIME 类型
    return Response(
        content=b"custom binary data",
        media_type="application/octet-stream",
        status_code=200
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.app_host, port=settings.import_app_port)