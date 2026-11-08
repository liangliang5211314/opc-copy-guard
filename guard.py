#!/usr/bin/env python3
"""Offline fixed-fact checker. Original educational example, no model calls."""
import argparse
import json
from pathlib import Path
import sys

MAX_BYTES = 1024 * 1024
BASE = Path(__file__).resolve().parent


class InputError(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        validate_unicode(key)
        if key in result:
            raise InputError(f"重复字段：{key}")
        result[key] = value
    return result


def validate_unicode(value):
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            raise InputError("文字含孤立 Unicode 代理项，请重新保存有效的 UTF-8 文字") from exc
    elif type(value) is dict:
        for key, item in value.items():
            validate_unicode(key)
            validate_unicode(item)
    elif type(value) is list:
        for item in value:
            validate_unicode(item)


def reject_constant(value):
    raise InputError(f"不支持的数字：{value}")


def load_json(path):
    # Read at most the limit plus one byte, including when size metadata changes.
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise InputError("单个文件不能超过 1 MiB")
        result = json.loads(raw.decode("utf-8-sig"),
                            object_pairs_hook=unique_object,
                            parse_constant=reject_constant)
        validate_unicode(result)
        return result
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise InputError(f"{Path(path).name}：{exc}") from exc


def validate_fixed(fixed, source):
    if type(fixed) is not dict or not fixed:
        raise InputError(f"{source}：固定信息必须是非空对象")
    if len(fixed) > 100:
        raise InputError(f"{source}：最多 100 项固定信息")
    for name, value in fixed.items():
        if not name.strip():
            raise InputError(f"{source}：字段名称不能为空")
        # Keep this beginner format deliberately small and exact.
        valid = ((type(value) is str and bool(value.strip())) or
                 (type(value) is int and value >= 0) or
                 (type(value) is list and bool(value) and
                  all(type(v) is str and bool(v.strip()) for v in value)))
        if not valid:
            raise InputError(f"{source}：{name} 只能是非空文字、非负整数或非空文字列表；金额请写成文字")


def validate_documents(baseline, draft):
    if type(baseline) is not dict or set(baseline) != {"固定信息"}:
        raise InputError("原始清单只允许顶层字段：固定信息")
    if type(draft) is not dict or set(draft) != {"标题", "介绍", "固定信息"}:
        raise InputError("待检查稿必须且只能包含：标题、介绍、固定信息")
    for key in ("标题", "介绍"):
        if type(draft[key]) is not str or not draft[key].strip():
            raise InputError(f"待检查稿：{key} 必须是非空文字")
    validate_fixed(baseline["固定信息"], "原始清单")
    validate_fixed(draft["固定信息"], "待检查稿")


def quoted(value):
    return json.dumps(value, ensure_ascii=False)


def differences(baseline, draft):
    validate_documents(baseline, draft)
    expected, actual = baseline["固定信息"], draft["固定信息"]
    found = []
    for key, value in expected.items():
        if key not in actual:
            found.append(f"{key}：缺失；原始值 {quoted(value)}")
        elif type(value) is not type(actual[key]) or value != actual[key]:
            found.append(f"{key}：原始值 {quoted(value)}；待检查值 {quoted(actual[key])}")
    for key in actual:
        if key not in expected:
            found.append(f"{key}：额外增加；待检查值 {quoted(actual[key])}")
    return found


def check(baseline_path, draft_path):
    baseline, draft = load_json(baseline_path), load_json(draft_path)
    found = differences(baseline, draft)
    if found:
        print(f"FAIL | {len(found)} 项固定信息不一致")
        for item in found:
            print(f"- {item}")
        print("先对照原始清单修改待检查稿，不要为通过检查改动原始清单。")
        return 1
    print(f"PASS | {len(baseline['固定信息'])} 项固定信息一致 | 标题和介绍仍需人工复核")
    return 0


def demo():
    baseline = load_json(BASE / "baseline.json")
    good = differences(baseline, load_json(BASE / "draft_good.json"))
    bad = differences(baseline, load_json(BASE / "draft_bad.json"))
    expected = ["价格（元）", "修改轮数", "交付内容"]
    if good or len(bad) != 3 or set(item.split("：", 1)[0] for item in bad) != set(expected):
        print("DEMO FAILED | 示例文件可能被改动，请重新下载原始示例")
        return 2
    print("DEMO OK | 正确示例通过 | 错误示例拦截 3 处")
    for item in bad:
        print(f"- {item}")
    print("范围：虚构数据的字段对照；未调用模型；不检查标题和介绍中的承诺。")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="检查 AI 改稿是否改动固定信息；不会修改文件")
    parser.add_argument("baseline", nargs="?", help="人工确认的原始清单")
    parser.add_argument("draft", nargs="?", help="待检查稿")
    parser.add_argument("--demo", action="store_true", help="运行自带虚构正确/错误样例")
    args = parser.parse_args(argv)
    if args.demo and (args.baseline or args.draft):
        parser.error("--demo 不能同时指定文件")
    if not args.demo and not (args.baseline and args.draft):
        parser.error("请指定原始清单和待检查稿，或使用 --demo")
    try:
        return demo() if args.demo else check(args.baseline, args.draft)
    except InputError as exc:
        print(f"INPUT ERROR | {exc}")
        print("先检查文件路径、UTF-8 编码和 JSON 格式；不要把整个 Markdown 代码围栏存进文件。")
        return 2


if __name__ == "__main__":
    sys.exit(main())
