# 在 PyCharm 里新建个临时脚本跑一下,或直接在 python 控制台粘
from app.infra.persistence.history_repository import history_repository as repo

sid = "test_history_001"
repo.save_message(session_id=sid, role="user", text="烫金机怎么调温度？")
repo.save_message(session_id=sid, role="assistant", text="通过面板旋钮设定……",
                  rewritten_query="HAK 180 烫金机如何调节温度",
                  item_names=["HAK 180 烫金机"],
                  image_urls=["http://localhost/img/panel.jpg"])
print("写完了")