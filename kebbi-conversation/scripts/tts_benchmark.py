#!/usr/bin/env python3
"""Run the realDebug TTS-only diagnostic over USB; analyze with Python stdlib only."""
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
import re
import statistics
import subprocess
import time

PACKAGE = "jp.ojimalab.kebbi.conversation"
ACTIVITY = "jp.ojimalab.kebbi.TtsBenchmarkActivity"
METRICS = {
    "sdk_start_wait_ms": ("request_ns", "start_callback_ns"),
    "sdk_call_ms": ("request_ns", "call_return_ns"),
    "notification_to_complete_ms": ("start_callback_ns", "complete_callback_ns"),
    "request_to_complete_ms": ("request_ns", "complete_callback_ns"),
}


def percentile(values, p):
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def summarize(records):
    protocols = [r for r in records if r.get("event") == "protocol"]
    if len(protocols) != 1:
        raise ValueError("exactly one protocol required")
    protocol = protocols[0]
    run_id = protocol["run_id"]
    cases = {c["id"]: c["text"] for c in protocol["cases"]}
    rows, seen = [], set()
    for record in records:
        if record.get("run_id") != run_id:
            raise ValueError("mixed run IDs")
        if record.get("event") != "trial":
            continue
        row = dict(record)
        key = (row["case_id"], row["repeat"], row["warmup"])
        if key in seen:
            raise ValueError("duplicate trial")
        seen.add(key)
        if row["case_id"] not in cases or row["text"] != cases[row["case_id"]]:
            raise ValueError("unexpected case")
        if type(row["warmup"]) is not bool:
            raise ValueError("warmup must be boolean")
        if row["repeat"] not in ([0] if row["warmup"] else range(1, protocol["repeats"] + 1)):
            raise ValueError("invalid repeat")
        if row["status"] == "ok":
            request, returned, start, complete = [row[k] for k in
                ("request_ns", "call_return_ns", "start_callback_ns", "complete_callback_ns")]
            if not (0 < request <= returned and request <= start <= complete and start > 0):
                raise ValueError("invalid timestamp ordering")
            # A callback can arrive before startTTS returns; do not require returned <= start.
            for name, (begin, end) in METRICS.items():
                row[name] = (row[end] - row[begin]) / 1_000_000
        rows.append(row)
    endings = [r for r in records if r.get("event") == "finished"]
    if len(endings) > 1:
        raise ValueError("duplicate completion")
    measured = [r for r in rows if not r["warmup"] and r["status"] == "ok"]
    groups = {}
    for name in ["all", *cases]:
        selected = [r for r in measured if name == "all" or r["case_id"] == name]
        groups[name] = {"n": len(selected)}
        for metric in METRICS:
            values = [r[metric] for r in selected]
            groups[name][metric] = None if not values else {
                "mean": statistics.mean(values), "median": statistics.median(values),
                "p95": percentile(values, .95), "min": min(values), "max": max(values),
            }
    complete = bool(endings and endings[0]["status"] == "complete")
    if complete and (len(rows) != len(cases) * (protocol["repeats"] + 1)
                     or any(r["status"] != "ok" for r in rows)):
        raise ValueError("incomplete run marked complete")
    return {"protocol": protocol, "complete": complete,
            "finish_status": endings[0]["status"] if endings else "running_or_interrupted",
            "successful_measured_trials": len(measured),
            "warmup_trials": sum(r["warmup"] for r in rows),
            "failed_trials": sum(r["status"] != "ok" for r in rows),
            "groups": groups, "trials": rows}


def save_report(records, destination):
    destination.mkdir(parents=True, exist_ok=True)
    result = summarize(records)
    (destination / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if result["trials"]:
        fields = list(dict.fromkeys(k for r in result["trials"] for k in r))
        with (destination / "trials.csv").open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(result["trials"])
    lines = ["# NUWA標準TTSの開始待ち時間", "",
        f"実行状態: {result['finish_status']} / 成功した本計測: {result['successful_measured_trials']}回。",
        "単位はms。ウォームアップと失敗試行は平均から除外。95パーセンタイルは線形補間。", "",
        "| 文章 | 文字数 | n | 開始待ち平均 | 中央値 | p95 | 最小 | 最大 | 開始通知〜完了 平均 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    cases = {c["id"]: c["text"] for c in result["protocol"]["cases"]}
    for name, group in result["groups"].items():
        if not group["n"]:
            continue
        stat = group["sdk_start_wait_ms"]
        values = [f"{stat[k]:.3f}" for k in ("mean", "median", "p95", "min", "max")]
        lines.append("| " + " | ".join([name, str(len(cases[name])) if name in cases else "—",
                     str(group["n"]), *values,
                     f"{group['notification_to_complete_ms']['mean']:.3f}"]) + " |")
    lines += ["", "計測区間は、Kebbi内の単調増加時計で記録したstartTTS直前〜最初のSTARTコールバック入口。",
              "SDKの処理・サービスとの通信・開始通知の配送を含みます。音声合成エンジン内部だけの処理時間や、実音声の音響的な開始時刻ではありません。",
              "LLM・ASR・ジェスチャー・動作準備・USB通信待ちは計測区間に入りません。",
              "同じ3文章を繰り返す通常稼働時の計測で、SDK/音声エンジンのキャッシュを消去していません。",
              "各文章1回のウォームアップを除外。最初の呼出しもtrials.csvに別記し、コールド起動の平均とは区別します。",
              "SDK通知にはリクエストIDがないため1件ずつ実行し、完了後750ms待機。失敗時は後続試行を中止します。",
              "", "## 固定文章", ""]
    lines.extend(f"- {key}（{len(text)}文字）: {text}" for key, text in cases.items())
    (destination / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--serial")
    parser.add_argument("--run-id")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--collect", action="store_true", help="Collect an already started run without restarting it")
    parser.add_argument("--analyze", type=Path, help="Analyze a downloaded JSONL file without a device")
    args = parser.parse_args()
    if args.analyze:
        records = [json.loads(line) for line in args.analyze.read_text(encoding="utf-8").splitlines() if line]
        print(json.dumps(save_report(records, args.output)["groups"], ensure_ascii=False))
        return
    run_id = args.run_id or "tts_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        parser.error("invalid run-id")
    if args.collect and not args.run_id:
        parser.error("--collect requires --run-id")
    adb = [args.adb] + (["-s", args.serial] if args.serial else [])

    def command(*parts):
        return subprocess.run([*adb, *parts], check=True, capture_output=True, timeout=20).stdout

    if command("get-state").strip() != b"device":
        raise RuntimeError("ADB device not connected")
    args.output.mkdir(parents=True, exist_ok=True)
    if not args.collect:
        # Preserve preferences/history: force-stop does not erase application data.
        command("shell", "am", "force-stop", PACKAGE)
        command("shell", "am", "start", "-W", "-n", PACKAGE + "/" + ACTIVITY, "--es", "run_id", run_id)
    (args.output / "run-id.txt").write_text(run_id + "\n", encoding="utf-8")
    print(f"run_id={run_id}; waiting for robot-side TTS diagnostic", flush=True)
    deadline, previous = time.monotonic() + 1200, -1
    while time.monotonic() < deadline:
        try:
            raw = command("exec-out", "run-as", PACKAGE, "cat", "files/tts-benchmark/" + run_id + ".jsonl")
        except subprocess.CalledProcessError:
            time.sleep(2)
            continue
        # A final line may still be in flight. Preserve it but parse only complete lines.
        (args.output / "device-trials.jsonl").write_bytes(raw)
        records = [json.loads(line) for line in raw.split(b"\n")[:-1] if line]
        count = sum(r.get("event") == "trial" for r in records)
        if count != previous:
            print(f"saved trials: {count}/33", flush=True)
            previous = count
        if any(r.get("event") == "finished" for r in records):
            result = save_report(records, args.output)
            print(f"finished: {result['finish_status']}; report: {args.output / 'report.md'}", flush=True)
            if not result["complete"]:
                raise SystemExit(1)
            return
        time.sleep(2)
    raise SystemExit("Collection timed out; resume using --collect --run-id " + run_id)


if __name__ == "__main__":
    main()
