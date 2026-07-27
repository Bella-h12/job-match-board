#!/usr/bin/env python3
"""Regression tests for build_board.py. Run: python3 scripts/test_build.py

Every check that guards a build failure is written so it FAILS when the guard
is removed — a test that can only ever be green teaches you to ignore green.
"""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)

from build_board import BuildError, build  # noqa: E402

TEMPLATE = open(os.path.join(ROOT, "assets", "template.html"), encoding="utf-8").read()
EXAMPLE = json.load(
    open(os.path.join(ROOT, "examples", "board.example.json"), encoding="utf-8")
)

failures = []


def check(name, fn):
    try:
        fn()
        print(f"  ok   {name}")
    except AssertionError as ex:
        print(f"  FAIL {name}: {ex}")
        failures.append(name)
    except Exception as ex:  # noqa: BLE001
        print(f"  FAIL {name}: 未预期的异常 {type(ex).__name__}: {ex}")
        failures.append(name)


def rejects(data, fragment):
    """Assert the build refuses this data and says why."""
    try:
        build(data, TEMPLATE)
    except BuildError as ex:
        assert fragment in str(ex), f"报错信息里没有 {fragment!r}，实际是：{ex}"
        return
    raise AssertionError(f"本该报错（{fragment}）却构建成功了")


def mutate(**changes):
    d = copy.deepcopy(EXAMPLE)
    d.update(changes)
    return d


# --- 正例 ---------------------------------------------------------------

def t_example_builds():
    out = build(copy.deepcopy(EXAMPLE), TEMPLATE)
    assert "Northwind Labs" in out, "示例公司没出现在成品里"
    assert "{{" not in out, "还有没替换的占位符"


def t_payload_is_valid_json():
    out = build(copy.deepcopy(EXAMPLE), TEMPLATE)
    m = re.search(
        r'<script id="board-data" type="application/json">(.*?)</script>', out, re.S
    )
    assert m, "找不到 board-data 数据块"
    payload = json.loads(m.group(1))
    assert len(payload["jobs"]) == len(EXAMPLE["board"]), "岗位数对不上"
    assert payload["urls"], "URL 表是空的"


def t_every_board_row_renders():
    out = build(copy.deepcopy(EXAMPLE), TEMPLATE)
    m = re.search(
        r'<script id="board-data" type="application/json">(.*?)</script>', out, re.S
    )
    payload = json.loads(m.group(1))
    for j in payload["jobs"]:
        assert j["role"], f'{j["co"]} 少了 role'
        assert j["t"] in payload["tiers"], f'{j["co"]} 的分档 {j["t"]} 没有对应说明'


def t_empty_sections_drop_their_heading():
    d = mutate(salary=[], skips=[], leads=[], steps=[], changes=None)
    out = build(d, TEMPLATE)
    # 断言标题的标记，不是纯文字——"薪酬估算"四个字也会出现在正文里
    assert "<h2>薪酬估算</h2>" not in out, "薪酬为空时标题没有被删掉"
    assert "<h2>不投的岗位与原因</h2>" not in out, "不投清单为空时标题没有被删掉"
    assert "<h2>执行计划</h2>" not in out, "执行计划为空时标题没有被删掉"
    assert 'class="refresh"' not in out, "今日变化为空时那三栏没有被删掉"
    assert "Northwind Labs" in out, "删空标题时误伤了正文"
    # 有数据时标题必须在——否则上面四条会因为标题永远不存在而恒真
    full = build(copy.deepcopy(EXAMPLE), TEMPLATE)
    assert "<h2>薪酬估算</h2>" in full, "有薪酬数据时标题反而不见了"
    assert "<h2>执行计划</h2>" in full, "有执行计划时标题反而不见了"


def t_html_is_escaped_in_plain_fields():
    d = copy.deepcopy(EXAMPLE)
    d["board"][0]["company"] = 'Ev<il> & "Co"'
    out = build(d, TEMPLATE)
    m = re.search(
        r'<script id="board-data" type="application/json">(.*?)</script>', out, re.S
    )
    payload = json.loads(m.group(1))
    # 公司名走 JSON 通道，由前端 esc() 转义，这里确认原值完整传下去
    assert payload["jobs"][0]["co"] == 'Ev<il> & "Co"', "公司名在传递中被改坏了"
    assert "</script>" not in m.group(1), "数据块里出现了会截断 script 的字符串"


# --- 反例：每一条都必须变红 ----------------------------------------------

def t_rejects_missing_title():
    d = copy.deepcopy(EXAMPLE)
    del d["meta"]["title"]
    rejects(d, "$.meta.title")


def t_rejects_empty_verdict():
    rejects(mutate(verdict=[]), "verdict")


def t_rejects_bad_action_kind():
    d = copy.deepcopy(EXAMPLE)
    d["ranking"][0]["action_kind"] = "maybe"
    rejects(d, "action_kind")


def t_rejects_bad_light():
    d = copy.deepcopy(EXAMPLE)
    d["board"][0]["light"] = "blue"
    rejects(d, "light")


def t_rejects_bad_status():
    d = copy.deepcopy(EXAMPLE)
    d["board"][0]["status"] = "maybe-open"
    rejects(d, "status")


def t_rejects_bad_tier():
    d = copy.deepcopy(EXAMPLE)
    d["board"][0]["tier"] = "x"
    rejects(d, "tier")


def t_rejects_duplicate_company():
    d = copy.deepcopy(EXAMPLE)
    d["board"].append(copy.deepcopy(d["board"][0]))
    rejects(d, "重复")


def t_rejects_missing_tier_description():
    d = copy.deepcopy(EXAMPLE)
    del d["tiers"]["s"]
    rejects(d, "$.tiers.s")


def t_rejects_missing_role():
    d = copy.deepcopy(EXAMPLE)
    del d["board"][0]["role"]
    rejects(d, "role")


def t_rejects_bad_floor_kind():
    d = copy.deepcopy(EXAMPLE)
    d["salary"][0]["floor_kind"] = "great"
    rejects(d, "floor_kind")


def t_rejects_unfilled_placeholder():
    try:
        build(copy.deepcopy(EXAMPLE), TEMPLATE + "\n{{NOT_A_REAL_FIELD}}")
    except BuildError as ex:
        assert "NOT_A_REAL_FIELD" in str(ex), f"没点名漏掉的占位符：{ex}"
        return
    raise AssertionError("模板里留了未知占位符却构建成功了")


TESTS = [(k[2:], v) for k, v in sorted(globals().items()) if k.startswith("t_")]

if __name__ == "__main__":
    print(f"运行 {len(TESTS)} 条用例：")
    for name, fn in TESTS:
        check(name, fn)
    if failures:
        print(f"\n{len(failures)} 条失败：{', '.join(failures)}")
        sys.exit(1)
    print("\n全部通过。")
