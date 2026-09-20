"""
split_by_titles 验证脚本

业务代码在 app/rag/import_/split_service.py，这里只做检查。
跑法：
    cd ai_knowledge_base
    PYTHONPATH=. .venv/Scripts/python.exe test/test_split_by_titles.py

结构：
  第一部分【硬契约】有断言 —— 输赢明确，只看对错
  第二部分【观察项】只打印 —— 是你的设计取舍，脚本不下结论

设计说明：函数一旦抛异常就不再重复调用（否则 @step_log 会把同一个
         traceback 打 N 遍，把有用信息全淹掉），并直接指出出错行号。
"""

import re
import sys
from pathlib import Path

_passed: list[str] = []
_failed: list[str] = []
_skipped: list[str] = []
_最后错误 = ""
_出错位置 = ""
_已崩 = False


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        _passed.append(name)
        print(f"  [通过] {name}")
    else:
        _failed.append(name)
        print(f"  [失败] {name}")
        for line in str(detail).splitlines():
            if line.strip():
                print(f"         {line}")


def skip(name: str) -> None:
    _skipped.append(name)
    print(f"  [跳过] {name}")


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * 70)


print("=" * 70)
print("split_by_titles 验证脚本")
print("=" * 70)

print("\n[前置检查]")
try:
    from app.rag.import_ import split_service as ss
except Exception as exc:
    print(f"  导入失败：{exc}")
    sys.exit(1)

if not hasattr(ss, "split_by_titles"):
    print("  split_service.py 里还没有 split_by_titles，先写它。")
    sys.exit(0)
print("  split_by_titles 已找到")


def 切(md: str, title: str = "测试文档"):
    """安全调用。崩过一次就不再调用（避免 traceback 刷屏），并定位到业务文件的行号。"""
    global _最后错误, _出错位置, _已崩
    if _已崩:
        return None
    try:
        return ss.split_by_titles(md, title)
    except Exception as exc:
        tb, 命中 = exc.__traceback__, None
        while tb:
            if "split_service.py" in tb.tb_frame.f_code.co_filename:
                命中 = tb
            tb = tb.tb_next
        _出错位置 = f"split_service.py:{命中.tb_lineno}" if 命中 else "（不在 split_service.py 内）"
        _最后错误 = f"{type(exc).__name__}: {exc}"
        _已崩 = True
        return None


# ============================================================== 第一部分
section("第一部分【硬契约】—— 下面每条都该是「通过」")

out = 切("# 标题\n正文\n")
check(
    "调用 split_by_titles 不报错",
    out is not None,
    f"出错位置：{_出错位置}\n"
    f"异常：{_最后错误}\n"
    "  函数一进门就崩，后面所有检查都无法验证。先修这一处再跑。",
)

if out is None:
    for n in [
        "无标题文档 → 1 个 default 块，内容原样保留",
        "代码块内的 # 行不被当成标题",
        "围栏行本身留在块内容里",
        "标题+正文 的块，标题不会丢",
        "标题+正文 的块，正文都在",
        "每个块都有 content / title / file_title",
        "没有内容为空的块",
        "file_title 透传到每个块",
        "load_markdown_content 支持 str 类型的 md_path",
    ]:
        skip(n)
else:
    # 1. 全文没有标题 → default 兜底，内容原样保留
    无标题原文 = "这文档一个标题都没有。\n就两行普通文字。"
    out = 切(无标题原文)
    check(
        "无标题文档 → 1 个 default 块，内容原样保留",
        out is not None and len(out) == 1
        and out[0]["title"] == "default" and out[0]["content"] == 无标题原文,
        f"实际 {len(out)} 块，标题={[c.get('title') for c in out]}，"
        f"内容是否原样={bool(out) and out[0].get('content') == 无标题原文}",
    )

    # 2. 代码块里的 # 不能被当成标题（这是 is_code_block 的全部意义）
    out = 切("# 手册\n\n```python\n# 注释A\nx = 1\n```\n\n## 尾巴\n正文\n")
    check(
        "代码块内的 # 行不被当成标题",
        out is not None and not any(c["title"].strip() == "# 注释A" for c in out),
        f"切出的标题={[c.get('title') for c in out]}\n"
        "  出现 '# 注释A' 作为标题 = 代码里的注释被误判成了标题",
    )

    # 3. 围栏行自己也要留在 content 里，否则代码块标记就丢了
    out = 切("# 手册\n\n```python\nx = 1\n```\n\n## 尾巴\n正文\n")
    围栏总数 = sum(c["content"].count("```") for c in out) if out else 0
    check(
        "围栏行本身留在块内容里（代码块标记不丢）",
        围栏总数 >= 2,
        f"所有块里 ``` 一共出现 {围栏总数} 次（开+关应为 2 次）",
    )

    # 4. 标题后面有正文时，标题和正文都不能丢
    out = 切("# 甲\n\n甲的内容\n\n## 乙\n乙的内容\n")
    标题们 = [c["title"] for c in out] if out else []
    check(
        "标题+正文 的块，标题不会丢",
        标题们 == ["# 甲", "## 乙"],
        f"实际标题={标题们}，期望 ['# 甲', '## 乙']",
    )
    check(
        "标题+正文 的块，正文都在",
        out is not None and len(out) == 2
        and "甲的内容" in out[0]["content"] and "乙的内容" in out[1]["content"],
        f"各块 content={[c['content'] for c in out or []]}",
    )

    # 5. 字段结构
    out = 切("# 甲\n\n甲的内容\n")
    缺 = [i for i, c in enumerate(out or []) if not {"content", "title", "file_title"} <= set(c)]
    空 = [i for i, c in enumerate(out or []) if not c["content"].strip()]
    check("每个块都有 content / title / file_title", not 缺, f"缺字段的块下标 {缺}")
    check("没有内容为空的块", not 空, f"空内容块下标 {空}")

    # 6. file_title 透传（后面 Milvus 溯源靠它）
    out = 切("# 甲\n\n甲的内容\n", "我的手册")
    check(
        "file_title 透传到每个块",
        out is not None and all(c.get("file_title") == "我的手册" for c in out),
        f"实际={[c.get('file_title') for c in out or []]}",
    )

    # 7. load_markdown_content：state.py 里 md_path 声明是 str
    if hasattr(ss, "load_markdown_content"):
        try:
            r = ss.load_markdown_content({
                "md_content": "",
                "md_path": "output/hak180使用说明书/hak180使用说明书.md",
                "file_title": "手测",
            })
            check("load_markdown_content 支持 str 类型的 md_path", isinstance(r, tuple) and bool(r[0]),
                  f"返回={r!r}")
        except Exception as exc:
            check("load_markdown_content 支持 str 类型的 md_path", False,
                  f"异常：{type(exc).__name__}: {exc}\n"
                  "  state.py 里 md_path 是 str（不是 Path）。同一个函数里另一处用了\n"
                  "  Path(md_path).stem，读文件那处没套 Path()，两处不一致。")
    else:
        skip("load_markdown_content 支持 str 类型的 md_path")


# ============================================================== 第二部分
section("第二部分【观察项】—— 只打印，是你的设计取舍，自己判断")

真实md = Path("output/hak180使用说明书/hak180使用说明书.md")
md = 真实md.read_text(encoding="utf-8") if 真实md.exists() else ""

# ---- A. 空行 continue 带来的行为变化
print("\n  A. 你把空行 continue 掉了，这是它带来的行为变化：\n")
if _已崩:
    print(f"     (函数无法调用，跳过：{_最后错误})")
else:
    for name, doc in [
        ("标题→空行→标题（该标题没正文）", "# 甲\n\n## 乙\n乙的内容\n"),
        ("标题→空行→正文",               "# 甲\n\n甲的内容\n"),
        ("标题→正文（中间无空行）",        "# 甲\n甲的内容\n"),
    ]:
        out = 切(doc)
        print(f"     {name}")
        print(f"       原文: {doc!r}")
        print(f"       {len(out)} 块: " + " | ".join(f"{c['title']!r} => {c['content']!r}" for c in out))
        print()
    print("     ↑ 第 1 种情况下 '# 甲' 整个消失了（教案版会留下 '# 甲\\n'）")
    print("       好处：len(...) > 1 那道门槛终于真的生效了，光杆标题会被过滤")
    print("       代价：见 B、C\n")

# ---- B / C. 真实文档
if not md:
    print("  (找不到 output/hak180使用说明书/hak180使用说明书.md，跳过 B、C)")
elif _已崩:
    print(f"  (函数无法调用，跳过 B、C：{_最后错误})")
else:
    out = 切(md, "hak180使用说明书")
    lens = [len(c["content"]) for c in out]
    print(f"  B. 真实文档切出 {len(out)} 块（教案版同一步是 91 个 section）")
    print(f"     max={max(lens)} min={min(lens)} avg={sum(lens) // len(lens)}")
    print(f"     含空行(\\n\\n)的块：{sum(1 for c in out if chr(10) * 2 in c['content'])} / {len(out)}")
    print("     ↑ 这条重点看：下一步 _split_long_section 的切分器把 \"\\n\\n\"（段落）排在")
    print("       分隔符优先级第一位。块内容里一个 \\n\\n 都没有，段落级切分就永远用不上，")
    print("       只能退到按 \\n 或标点硬切。\n")

    HREG = re.compile(r"^\s*#{1,6}\s.+")
    lines = md.replace("\r\n", "\n").split("\n")
    in_code, hs = False, []
    for i, raw in enumerate(lines):
        s = raw.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_code = not in_code
            continue
        if HREG.match(s) and not in_code:
            hs.append((i, s))
    丢掉 = []
    for k, (i, s) in enumerate(hs):
        end = hs[k + 1][0] if k + 1 < len(hs) else len(lines)
        if not [l for l in lines[i + 1:end] if l.strip()]:
            丢掉.append(s)
    实际标题 = {c["title"] for c in out}
    真丢 = [t for t in 丢掉 if t not in 实际标题]
    print(f"  C. 全文档 {len(hs)} 个标题里，「后面只有空行、没有正文」的 {len(丢掉)} 个：")
    for t in 丢掉:
        print(f"       {t!r}" + ("   ← 确实被丢了" if t in 真丢 else "   ← 走收尾，侥幸留下"))
    print(f"\n     实际消失 {len(真丢)} 个。注意里面有些是**真标题**（'## 简介'、'## 故障排除'、")
    print("     '## 11 附录'），它们不是假标题，只是自身没正文、正文都在子标题里。")

# ---- D. 日志噪音（不需要调用函数）
if md:
    空行数 = sum(1 for l in md.split("\n") if not l.strip())
    print(f"\n  D. 日志噪音：空行那条你打成了 logger.warning")
    print(f"     这份文档有 {空行数} 个空行 → 会打出约 {空行数} 条 WARNING。")
    print(f"     空行是极常见情况，warning 级别会把真正的警告淹掉。")


# -------------------------------------------------------------- 汇总
section("汇总")
print(f"  通过 {len(_passed)} 条，失败 {len(_failed)} 条，跳过 {len(_skipped)} 条")
if _failed:
    print(f"  失败项：")
    for n in _failed:
        print(f"    - {n}")
if _skipped:
    print(f"  跳过项（函数无法调用，未验证）：")
    for n in _skipped:
        print(f"    - {n}")
sys.exit(1 if _failed else 0)
