"""
node_document_split 验证脚本

这只是一个「检查工具」，不含任何业务逻辑。业务代码在：
    app/rag/import_/split_service.py   ← 你自己写

跑法（命令行跑 test/ 下的文件要带 PYTHONPATH）：
    cd ai_knowledge_base
    PYTHONPATH=. .venv/Scripts/python.exe test/test_split_service.py

结构：
  第一部分【硬契约】有断言 —— 输赢明确，只看对错
  第二部分【观察项】只打印 —— 切得好不好是要人判断的，脚本不下结论

注意：跑第一部分第 7 条会真的调用 split_document()，
      副作用是往 md 所在目录写一个 chunks.json（这是节点本身的正常行为）。
"""

import sys
from pathlib import Path

# ---------------------------------------------------------------- 小工具

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    """一条断言。只记录结果、不中断，让一次跑完能拿到完整清单。"""
    if cond:
        _passed.append(name)
        print(f"  [通过] {name}")
    else:
        _failed.append(name)
        print(f"  [失败] {name}")
        for line in str(detail).splitlines():
            if line.strip():
                print(f"         {line}")


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * 68)


# ---------------------------------------------------------------- 前置检查
# 业务代码还没写时，给一句人话，而不是甩一个 traceback

print("=" * 68)
print("node_document_split 验证脚本")
print("=" * 68)

print("\n[前置检查]")

try:
    from app.rag.import_ import split_service as ss
except Exception as exc:
    print(f"  导入 split_service 失败：{exc}")
    sys.exit(1)

需要实现的函数 = [
    "load_markdown_content",
    "split_by_titles",
    "_split_long_section",
    "_merge_short_sections",
    "refine_chunks",
    "backup_chunks",
    "split_document",
]
missing = [n for n in 需要实现的函数 if not hasattr(ss, n)]
if missing:
    print(f"  split_service.py 里还没有这些函数：{missing}")
    print("  照着教案 5.4 节把它们写出来，再跑一次本脚本。")
    sys.exit(0)

try:
    from app.rag.import_.config import CHUNK_MAX_SIZE, CHUNK_SIZE
except Exception as exc:
    print(f"  从 config.py 读切块常量失败：{exc}")
    print("  教案 5.4「配置说明」要求加 CHUNK_MAX_SIZE / CHUNK_SIZE / CHUNK_OVERLAP 三个常量。")
    sys.exit(0)

print(f"  7 个函数都在；CHUNK_MAX_SIZE={CHUNK_MAX_SIZE}  CHUNK_SIZE={CHUNK_SIZE}")


# ================================================================ 第一部分
section("第一部分【硬契约】—— 有断言，下面每条都该是「通过」")

# 1. 全文没有标题 → default 兜底，内容不能丢
无标题原文 = "这文档一个标题都没有。\n就两行普通文字。"
out = ss.split_by_titles(无标题原文, "无标题文档")
check(
    "无标题文档兜底成 1 个 default 块，且内容原样保留",
    len(out) == 1 and out[0]["title"] == "default" and out[0]["content"] == 无标题原文,
    f"实际 {len(out)} 块，标题={[c.get('title') for c in out]}\n"
    f"内容是否原样保留：{bool(out) and out[0].get('content') == 无标题原文}",
)

# 2. 代码块里的 # 不是标题
代码块文档 = "## 真标题\n\n说明文字。\n\n```python\n# 这是代码注释，不是标题\nprint(1)\n```\n\n结尾。\n"
out = ss.split_by_titles(代码块文档, "代码块文档")
check(
    "代码块内的 # 不被当成标题（全文仍只有 1 个块）",
    len(out) == 1,
    f"实际切成 {len(out)} 块，标题={[c.get('title') for c in out]}\n"
    "说明：代码块里的 # 如果被当标题，块数会变多。",
)

# 3. 超长块（正文有句号/换行，属于正常情况）要被切短
out = ss.refine_chunks(
    [{"title": "## 长块", "content": "## 长块\n\n" + "这是一句话。" * 200, "file_title": "t"}],
    max_len=CHUNK_MAX_SIZE,
    min_len=CHUNK_SIZE,
)
最长 = max(len(c["content"]) for c in out)
check(
    f"超长块(有正常标点)被切到 <= {CHUNK_MAX_SIZE}",
    最长 <= CHUNK_MAX_SIZE,
    f"实际最长 {最长} 字",
)

# 4. 超长块（正文没有任何分隔符）也要被切短
#    ← 这条是重点：langchain 0.x 会自动补一个「按字符硬拆」的兜底分隔符，1.x 不会。
#      本项目装的是 1.x，所以照抄教案就可能让这条挂掉。
out = ss.refine_chunks(
    [{"title": "## 长块", "content": "## 长块\n\n" + "A" * 1500, "file_title": "t"}],
    max_len=CHUNK_MAX_SIZE,
    min_len=CHUNK_SIZE,
)
最长 = max(len(c["content"]) for c in out)
check(
    f"超长块(一个标点都没有)也被切到 <= {CHUNK_MAX_SIZE}",
    最长 <= CHUNK_MAX_SIZE,
    f"实际最长 {最长} 字，说明整段没被切开。\n"
    "  排查方向：RecursiveCharacterTextSplitter 的 separators 列表末尾有没有\n"
    "  「按字符硬拆」的那个兜底分隔符。langchain-text-splitters 0.x 会自动补上，\n"
    "  1.x 不会 —— 而本项目是 1.1.1。可以自己写个小例子验证切分器的行为。",
)

# 5. 同一个 parent_title 下的短块要合并
短块甲 = {"title": "## 甲-1", "content": "## 甲\n\n很短一。", "parent_title": "## 甲", "part": 1, "file_title": "t"}
短块乙 = {"title": "## 甲-2", "content": "## 甲\n\n很短二。", "parent_title": "## 甲", "part": 2, "file_title": "t"}
out = ss._merge_short_sections([短块甲, 短块乙], min_length=CHUNK_SIZE, max_length=CHUNK_MAX_SIZE)
check(
    "同 parent_title 的两个短块会合并成 1 个",
    len(out) == 1,
    f"实际 {len(out)} 块",
)

# 6. 最终每个 Chunk 字段齐全 —— 下游 Milvus 的 schema 靠它们
必填字段 = {"content", "title", "file_title", "parent_title", "part"}
out = ss.refine_chunks(
    [
        {"title": "## 长块", "content": "## 长块\n\n" + "这是一句话。" * 200, "file_title": "t"},
        {"title": "## 短块", "content": "## 短块\n\n就一句。", "file_title": "t"},
    ],
    max_len=CHUNK_MAX_SIZE,
    min_len=CHUNK_SIZE,
)
缺字段 = [i for i, c in enumerate(out) if not 必填字段 <= set(c.keys())]
空内容 = [i for i, c in enumerate(out) if not c["content"].strip()]
空父标题 = [i for i, c in enumerate(out) if not c["parent_title"]]
check("每个 Chunk 都有 content/title/file_title/parent_title/part", not 缺字段, f"缺字段的块下标 {缺字段}")
check("没有空内容的 Chunk", not 空内容, f"空内容块下标 {空内容}")
check("parent_title 不为空（Milvus 必填）", not 空父标题, f"空 parent_title 的块下标 {空父标题}")

# 7. split_document 要回写 state，并落盘 chunks.json
from app.shared.runtime.logger import PROJECT_ROOT  # noqa: E402

真实md = PROJECT_ROOT / "output" / "hak180使用说明书" / "hak180使用说明书.md"
if not 真实md.exists():
    print(f"  [跳过] split_document 端到端：找不到 {真实md}")
else:
    state = {
        "md_path": str(真实md),
        "task_id": "test_task_123456",
        "md_content": "",
        "file_title": "hak180使用说明书",
        "local_dir": str(PROJECT_ROOT / "output"),
    }
    final = ss.split_document(state)
    chunks = final.get("chunks", [])
    check("split_document 把结果回写到 state['chunks']", bool(chunks), "state['chunks'] 还是空的")
    check(
        "split_document 落盘了 chunks.json",
        (真实md.parent / "chunks.json").exists(),
        f"没找到 {真实md.parent / 'chunks.json'}",
    )


# ================================================================ 第二部分
section("第二部分【观察项】—— 只打印，不下结论，数字好坏自己判断")

if 真实md.exists():
    md内容 = 真实md.read_text(encoding="utf-8")
    粗切 = ss.split_by_titles(md内容, "hak180使用说明书")
    最终 = ss.refine_chunks(list(粗切), max_len=CHUNK_MAX_SIZE, min_len=CHUNK_SIZE)

    import re

    HREG = re.compile(r"^\s*#{1,6}\s.+")
    长度 = [len(c["content"]) for c in 最终]
    多标题 = [c for c in 最终 if sum(1 for ln in c["content"].split("\n") if HREG.match(ln.strip())) > 1]

    print(f"\n  真实文档：{真实md.name}")
    print(f"    粗切 {len(粗切)} 个 section  →  最终 {len(最终)} 个 Chunk")
    print(f"    长度   max={max(长度)}  min={min(长度)}  avg={sum(长度) // len(长度)}")
    print(f"    超过 CHUNK_MAX_SIZE 的：{sum(1 for x in 长度 if x > CHUNK_MAX_SIZE)} 个")
    print(f"    含 2 个以上标题行的：{len(多标题)} 个（占 {len(多标题) * 100 // len(最终)}%）")

    print(f"\n    最短的 3 个 Chunk（太短就是碎片，想想它值不值得占一个向量位）：")
    for c in sorted(最终, key=lambda x: len(x["content"]))[:3]:
        print(f"      len={len(c['content']):4d}  title={c['title']!r}  content={c['content'][:50]!r}")

    print(f"\n    跨标题最严重的一个（元数据 title 只指向第一段，检索会不准）：")
    if 多标题:
        c = max(多标题, key=lambda x: len(x["content"]))  # 注意按「内容长度」比，不是按字典键个数
        标题们 = [ln.strip() for ln in c["content"].split("\n") if HREG.match(ln.strip())]
        print(f"      len={len(c['content'])}  元数据 title={c['title']!r}")
        print(f"      内容里实际有 {len(标题们)} 个标题：{标题们}")

# 跨标题合并的最小复现：两个【不同标题】的短块，都没有 parent_title
print("\n  最小复现：两个不同标题的短块，会被合并吗？")
甲 = {"title": "## 章节甲", "content": "## 章节甲\n\n甲的内容很短。", "file_title": "d"}
乙 = {"title": "## 章节乙", "content": "## 章节乙\n\n乙的内容也很短。", "file_title": "d"}
结果 = ss._merge_short_sections([甲, 乙], min_length=CHUNK_SIZE, max_length=CHUNK_MAX_SIZE)
if len(结果) == 1:
    print(f"    → 合并成 1 块了。也就是说「只在同父标题下合并」这条没有真正生效：")
    print(f"      {结果[0]['content']!r}")
    print(f"      split_by_titles 产出的 section 没有 parent_title 这个键，两边 .get() 都是 None，")
    print(f"      None == None 成立，于是不同章节也被合并。")
    print(f"      注意：这未必是坏事 —— 它顺手把碎块粘起来了。要不要改，先看上面的长度分布。")
else:
    print(f"    → 没合并，输出 {len(结果)} 块（说明「同父标题」是按 title 之类比较的）")


# ---------------------------------------------------------------- 汇总
section("汇总")
print(f"  通过 {len(_passed)} 条，失败 {len(_failed)} 条")
if _failed:
    print("  失败项：")
    for n in _failed:
        print(f"    - {n}")

sys.exit(1 if _failed else 0)
