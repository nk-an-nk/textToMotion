#!/usr/bin/env python3
"""Summarize measured artifacts without extrapolating RTX 5070 or quality scores."""
import argparse
import csv
from datetime import datetime,timezone
import hashlib
import html
import json
from pathlib import Path
import statistics

MODELS=['molingo','remomask2','momask']
LABELS={'molingo':'MoLingo-263','remomask2':'ReMoMask-2','momask':'MoMask'}
PROFILES={'lab_proxy':'RTX 4090 / VRAM上限12GB','b300':'B300'}


def write_csv(path,rows):
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');writer.writeheader();writer.writerows(rows)


def tilt(motion):
    import math
    angles=[]
    for frame in motion['positions']:
        v=[b-a for a,b in zip(frame[0],frame[6])];n=math.sqrt(sum(x*x for x in v))
        angles.append(math.degrees(math.acos(max(-1,min(1,v[1]/n)))))
    return max(angles)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('reports/masked-models-20261016'))
    p.add_argument('--state-root',type=Path,default=Path('.motion-lab/masked-models-20261016'))
    p.add_argument('--require-videos',action='store_true');a=p.parse_args();root=a.root;root.mkdir(parents=True,exist_ok=True)
    plan=json.loads(Path('configs/masked_comparison_20261016.json').read_text())
    summaries=[];segments=[];trials=[];dialogues=[];videos=[];hardware=[];retained=[];machines=[]
    for profile in PROFILES:
        state=json.loads((a.state_root/profile/'state.json').read_text());rate=state['cost_per_hour_usd']
        retained.append({k:state.get(k) for k in ['pod_id','profile','stop_confirmed','stopped_at_utc','retention_until_utc','volume_gb','cost_per_hour_usd']})
        machine=json.loads((root/profile/'machine.json').read_text());cpu=next(row['data'] for row in json.loads(machine['lscpu'])['lscpu'] if row['field']=='Model name:')
        machines.append({'profile':profile,'cpu':cpu,'allocated_vcpu':state['allocated_vcpu'],'allocated_ram_gb':state['allocated_ram_gb'],'nvidia_smi':machine['nvidia_smi'].strip(),'image':state['image'],'gpu_hourly_usd':rate})
        for model in MODELS:
            native=root/profile/'native'/model
            if not (native/'measurements.json').exists():raise ValueError('Missing native measurements: '+str(native))
            rows=json.loads((native/'measurements.json').read_text());h=json.loads((native/'hardware.json').read_text());hardware.append(h)
            if len(rows)!=15:raise ValueError('Five inputs times three measured seeds are required.')
            for row in rows:
                trials.append({k:v for k,v in row.items() if not isinstance(v,(dict,list))})
            for unit in plan['segments']:
                sample=[x['skeleton_seconds'] for x in rows if x['id']==unit['id']]
                if len(sample)!=3:raise ValueError('Missing segment repeat.')
                source=native/unit['id']/'motion.json'
                segments.append({'profile':profile,'model':model,'segment':unit['id'],'original_text':unit['text'],
                    'english_motion_input':unit['motion_prompt'],'shared_llm_translation_seconds':unit['translation']['translation_seconds'],
                    'generation_median_seconds':statistics.median(sample),'generation_min_seconds':min(sample),'generation_max_seconds':max(sample),
                    'shared_translation_plus_native_stage_sum_seconds':unit['translation']['translation_seconds']+statistics.median(sample),
                    'stage_sum_is_measured_end_to_end':False,
                    'source_max_torso_tilt_degrees_seed0':tilt(json.loads(source.read_text()))})
            d=json.loads((root/profile/'dialogue'/model/'measurement.json').read_text());dialogues.append(d)
            motion=json.loads((root/profile/'dialogue'/model/'generated/01/motion.json').read_text())
            sample=[x['skeleton_seconds'] for x in rows];s={'profile':profile,'model':model,'gpu':h['gpu'],'trials':len(sample),
                'generation_median_seconds':statistics.median(sample),'generation_min_seconds':min(sample),'generation_max_seconds':max(sample),
                'cold_model_load_seconds':h['model_load_seconds'],'peak_vram_mib':max(x['peak_torch_allocated_mib'] for x in rows),
                'peak_process_ram_mib':max(x['process_peak_ram_mib'] for x in rows),'cpu_threads':h['cpu_threads'],
                'realtime_first_audio_seconds':d['first_teacher_audio_seconds_after_student_end'],
                'dialogue_llm_translation_seconds':d['translation_seconds'],'dialogue_native_generation_seconds':d['motion_generation_seconds'],
                'dialogue_bones_after_student_end_seconds':d['bone_ready_observed_seconds_after_student_end'],
                'dialogue_gap_from_realtime_seconds':d['bone_minus_first_realtime_audio_seconds'],
                'source_dialogue_max_torso_tilt_degrees':tilt(motion),
                'gpu_hourly_usd':rate,'native_generation_only_estimated_usd_per_request':rate*statistics.median(sample)/3600,
                'actual_lab_pc_measured':False,'full_body_inference_upper_body_display':True}
            summaries.append(s)
            for kind in ['common','dialogue']:
                folder=root/profile/(kind+'-video')/model;mp4=folder/('combined.mp4' if kind=='common' else 'dialogue.mp4');meta=mp4.with_suffix('.json')
                if not mp4.exists() or not meta.exists():
                    if a.require_videos:raise ValueError('Video is not complete: '+str(mp4))
                    continue
                v=json.loads(meta.read_text())
                if hashlib.sha256(mp4.read_bytes()).hexdigest()!=v['video_sha256']:raise ValueError('Video checksum mismatch.')
                videos.append({'profile':profile,'model':model,'kind':kind,'video':str(mp4.relative_to(root)),
                    'sha256':v['video_sha256'],'render_seconds':v['render_wall_seconds'],
                    'duration_seconds':v['plan']['duration_seconds'] if kind=='dialogue' else v['media']['format']['duration']})
    write_csv(root/'summary.csv',summaries);write_csv(root/'segment-times.csv',segments);write_csv(root/'all-trials.csv',trials)
    (root/'summary.json').write_text(json.dumps({'schema':'motion-lab/masked-model-comparison-v1','generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'summary':summaries,'machines':machines,'hardware':hardware,'dialogues':dialogues,'videos':videos,'retained_pods':retained},ensure_ascii=False,indent=2)+'\n')
    cost_table=['| 環境 | モデル | 常駐生成1回のGPU料金目安（共通区間中央値） | 会話の骨格生成1回 |','|---|---|---:|---:|']
    for row in summaries:cost_table.append(f"| {PROFILES[row['profile']]} | {LABELS[row['model']]} | ${row['native_generation_only_estimated_usd_per_request']:.6f} | ${row['gpu_hourly_usd']*row['dialogue_native_generation_seconds']/3600:.6f} |")
    specs=['| 環境 | 実CPU | 割当vCPU / 推論スレッド | 割当RAM | GPU / driver / VRAM / 電力上限 | GPU時給 |','|---|---|---|---:|---|---:|']
    for m in machines:specs.append(f"| {PROFILES[m['profile']]} | {m['cpu']} | {m['allocated_vcpu']} / 8 | {m['allocated_ram_gb']}GB | {m['nvidia_smi']} | ${m['gpu_hourly_usd']:.2f}/h |")
    inputs=['| 区間 | 元の発話 | LLMによる英語入力 | 英訳秒 |','|---|---|---|---:|']
    for u in plan['segments']:inputs.append(f"| {u['id']} | {u['text']} | {u['motion_prompt']} | {u['translation']['translation_seconds']:.3f} |")
    table=['| 環境 | モデル | 骨格生成中央値 | 会話の英訳 | 会話の骨格生成 | 発話終了→骨格受信 | Realtimeとの差 | VRAM最大 |','|---|---|---:|---:|---:|---:|---:|---:|']
    for s in summaries:table.append(f"| {PROFILES[s['profile']]} | {LABELS[s['model']]} | {s['generation_median_seconds']:.3f}s | {s['dialogue_llm_translation_seconds']:.3f}s | {s['dialogue_native_generation_seconds']:.3f}s | {s['dialogue_bones_after_student_end_seconds']:.3f}s | +{s['dialogue_gap_from_realtime_seconds']:.3f}s | {s['peak_vram_mib']/1024:.2f}GiB |")
    links=['| 環境 | モデル | 共通5区間 | 生徒→先生会話 |','|---|---|---|---|']
    for s in summaries:
        prefix=s['profile'];m=s['model'];links.append(f"| {PROFILES[prefix]} | {LABELS[m]} | [MP4]({prefix}/common-video/{m}/combined.mp4) | [MP4]({prefix}/dialogue-video/{m}/dialogue.mp4) |")
    retained_lines=[]
    for r in retained:retained_lines.append(f"- {r['profile']}: Pod `{r['pod_id']}`、停止確認 `{r['stop_confirmed']}`、保持期限 UTC `{r['retention_until_utc']}`。")
    full_cost_note='## 会話1リクエストの参考小計\n\nGPUは生徒音声開始から骨格受信までを按分し、今回のRealtime音声とLLM英訳の実usageからAPI料金を概算。1USD=200円。ASR・起動・待機・保存・描画は別。API単価は既存資料で2026-10-15確認のgpt-realtime-2.1（100万tokenあたり入力text4/audio32、出力text24/audio64 USD）を使用し、実請求とは未照合です。reasoningはtext内訳として二重加算しません。\n\n| 環境 | モデル | GPU按分 | Realtime音声 | LLM英訳 | 参考小計 |\n|---|---|---:|---:|---:|---:|\n| lab_proxy | molingo | 0.399円 | 1.783円 | 0.502円 | 2.684円 |\n| lab_proxy | remomask2 | 0.257円 | 1.886円 | 0.233円 | 2.376円 |\n| lab_proxy | momask | 0.259円 | 1.830円 | 0.290円 | 2.379円 |\n| b300 | molingo | 4.823円 | 1.762円 | 0.386円 | 6.972円 |\n| b300 | remomask2 | 3.452円 | 1.818円 | 0.295円 | 5.565円 |\n| b300 | momask | 3.055円 | 1.730円 | 0.305円 | 5.090円 |\n\n[計算原本と単価](request-cost-estimates.json)。\n\n'
    text='''# MoLingo / ReMoMask-2 / MoMask 実測比較（2026-10-16）

日本語・混在文をLLM（OpenAI Realtime、テキスト出力）で英訳し、その英語を動作モデルへ渡しました。音声・字幕は元の日本語と英語を保持しています。

## 測定結果

'''+ '\n'.join(table)+'''

骨格生成中央値は共通5区間×3 seed＝15回の常駐推論。テキスト符号化、学習済み生成、デコード、CPUへの転送、骨格JSONの直列化を含み、モデル読込・英訳・通信・保存・MP4描画を除きます。5区間それぞれのウォームアップを先に実施しました。seedは0/1/2、動画にはseed0を採用し、見栄えによる選び直しをしていません。

会話は各モデル・環境1回の測定です。1.9秒の録音済み合成生徒音声「先生、こんにちは！」をPCM16/24kHz/monoで実時間送信し、受信した教師の全文をLLMで英訳してから新規骨格を生成しました。「発話終了→骨格受信」は同じクライアントのmonotonic時計で計測し、Realtime応答、英訳、通信を含みます。「Realtimeとの差」は骨格受信と最初の音声チャンク受信の差で、スピーカー実再生との比較ではありません。

教師の返答は「こんにちは！今日も元気そうだね！英会話の練習を始めましょう」に固定しています。自由回答の性能評価ではありません。受信した文の英訳は毎回新規に実行し、各 `dialogue/MODEL/translation.json` に原文・英訳・翻訳秒数・API usageを残しました。英訳の表現と発話時間には呼び出しごとの揺れがあるため、厳密に同一の英語入力での速度比較は共通5区間を参照してください。

## デモ動画（12本）

[ブラウザーで全動画と計測表を見る](index.html)。正面1920×1080、30fps、H.264 CRF16、AAC192k。共通5区間は区間ごとに発話・動作を同じフレームで開始して連結しています。区間単独の30本のMP4も各 `common-video/MODEL/segments/01..05/video.mp4` にあります。

会話動画は実測した待ち時間を省略せず再現するオフライン動画です。教師音声を骨格受信まで保留して、発話と動作を同時に開始します。ライブ録画ではありません。描画はこのクラウド環境のCPU / SwiftShaderで実施しており、GPU推論時間と動画化時間を分けて保存しています。

'''+ '\n'.join(links)+'''

## 入力と英訳

共通5区間は同じ英訳・同じ実音声を全モデル・全GPUで共有しました。元の音声は2026-10-14の実生成クリップで、今回の推論開始前から保存済みです。英訳時間は下表に別記しており、共通区間の常駐推論中央値へ加算していません。`segment-times.csv` には英訳時間＋骨格生成中央値の処理時間合計も載せていますが、これは別測定の加算値であり、日本語入力からの通し実測ではありません。通し実測は会話の値を参照してください。

'''+ '\n'.join(inputs)+'''

## 条件と解釈

'''+ '\n'.join(specs)+'''

ソフトウェアは両方Ubuntu24.04の同一イメージ、Python3.12.3、PyTorch2.8.0+cu129 / CUDA12.9です。GPU欄のVRAMはnvidia-smiのMiB値で、公称288GB等とは単位が異なります。

- 研究室実機（Ryzen 7 5700X、RTX 5070 12GB、RAM32GB、Windows）には接続していません。代替はRTX 4090、PyTorch VRAM allocator上限12,227MiB、CPU8スレッド・affinity8です。GPUの演算性能、CPU型番、OSは一致せず、RAM32GBの強制上限も設けていません。RTX 5070の速度としては報告できません。
- B300は前回と同じNVIDIA B300 SXM6 AC 1枚。両環境で動作本体FP32、TF32無効、CPU8スレッド、同一ソースと重みです。MoMask / ReMoMask-2のCLIPには公式実装どおりFP16を併用し、MoLingoのT5はFP32です。動画中のFP32表記は動作本体を指します。実際のCPU型番、OS、driver、割当RAMは各環境の `machine.json` と `hardware.json`、導入パッケージは `versions.txt` に保存しています。
- MoLingoは公式HumanML3D **263次元版**（EMA、32 RF step、acceleration3、CFG5.5）。272次元版との比較ではありません。ReMoMask-2は公式epoch309、10 step、CFG4、retrieval k1/pool10。MoMaskはmasked18 step/CFG4＋residual CFG5。ソースcommitとダウンロードSHA256は [asset manifest](../../configs/masked_assets_20261016.json)。
- 3モデルとも全身22関節を実生成し、表示時に上半身を使用します。腰・脚の固定と胴体のyaw補正は表示用変換です。上半身だけ推論した速度ではありません。元の骨格JSONとHumanML3D特徴量NPYを `native/MODEL/` に保持しています。22関節に手指・表情の生成は含まれず、口パクは音声RMSに基づく表示です。
- 英訳後のMoLingo/T5では未知語0件を確認しました。CLIPを使う残り2モデルも入力を切り詰めず検証しています。英訳は動作指示文への書き換えを行っていません。
- これらは主に動作記述から全身運動を作るモデルです。発話内容の英訳だけでは会話ジェスチャーを保証できません。MoMaskの会話出力には大きく体を倒す動作があり、共通5区間でもMoMask/ReMoMask-2に大きな傾きが出ました。各seed0の胴体傾斜角をCSVに記録しています。傾斜角は品質点数ではなく、姿勢確認用の値です。FIDや意味適合度の定量評価は実施していません。
- 会話はJupyter WSS中継で骨格を受信しています。本番アプリの最適化済み直結通信とは異なるため、native推論秒数と通し実測を分けて評価してください。
- `summary.csv` の1リクエスト当たりGPU料金は **常駐した生成処理の秒数×GPU時給÷3600** の参考値です。起動・ダウンロード・待機・モデル読込・通信・保持領域・OpenAI利用料を含む実請求額ではありません。APIのusageは記録していますが、実請求額は未取得です。

## 生成処理のGPU料金目安

'''+ '\n'.join(cost_table)+'''

この表はGPUがすでに常駐し、生成中の時間だけを按分した参考値です。セットアップや待機も課金されるため、単発実験をこの金額で実行できるという意味ではありません。

''' + full_cost_note + '''
## ファイルと再現

- [集計CSV](summary.csv)、[区間別CSV](segment-times.csv)、[全90回の生データCSV](all-trials.csv)、[集計JSON](summary.json)、[整合チェック](validation.json)。
- [追加実験の全42動画ZIP](../masked-models-videos-20261016.zip)。12本の本編と30本の区間単独動画を収録しています。
- [今回のGPUレンタル概算](rental-estimate.json)。Pod作成から停止までを時給で計算すると合計約$4.29です。停止後の保存領域とOpenAI利用料は別で、実請求とは未照合です。
- 各 `native/MODEL/hardware.json` は重み読込・モデル構築の秒数を記録します。最初の推論を含むウォームアップ全体はこの値に含めておらず、起動から常駐準備完了までの総cold start時間は未集計です。各動画の同名JSONは描画時間、フレーム数、口パク、固定後の実描画骨の検証値を記録しています。
- 実行手順は [docs/masked_models.md](../../docs/masked_models.md)。既存の日本語直接入力の実験・コード・動画は保持しています。重み、トークン、VRM本体はGitへ追加していません。

## RunPodの保持

'''+ '\n'.join(retained_lines)+'''

停止したPodの永続ボリューム `/workspace/retained` に、元の重み、固定ソースと仮想環境のアーカイブ、実行コード、ログ、結果を保存しています。再開後は `/workspace/retained/resume.sh` で `/tmp/masked_runtime` を再構築できます。

24時間後の削除は、このクラウド環境で動くローカルwatcherによるbest effortです。RunPod側の強制TTLではなく、環境が停止・交換されるとwatcherも停止します。その場合はRunPod Consoleで期限を確認して削除するか、手順書のwatchコマンドを再開してください。チェックアウト外の共有領域にもprivate stateの控えを保存していますが、環境交換後の自動再開は検証していません。削除すると保持した環境データは失われます。
'''
    (root/'README.md').write_text(text)
    cards=[]
    for v in videos:
        label=PROFILES[v['profile']]+' / '+LABELS[v['model']]+' / '+('共通5区間' if v['kind']=='common' else '生徒→先生')
        segment_links=''
        if v['kind']=='common':segment_links='<p>区間別: '+' / '.join(f'<a href="{v["profile"]}/common-video/{v["model"]}/segments/{i:02}/video.mp4">{i}</a>' for i in range(1,6))+'</p>'
        cards.append('<article><h3>'+html.escape(label)+'</h3><video controls preload="none" poster="'+str(Path(v['video']).with_name('poster.jpg'))+'" src="'+v['video']+'"></video><p><a href="'+v['video']+'">MP4を開く</a> · 動画化 '+f'{v["render_seconds"]:.1f}'+'秒</p>'+segment_links+'</article>')
    html_table='<table><tr><th>環境 / モデル</th><th>骨格中央値</th><th>会話の英訳</th><th>発話終了→骨格</th><th>Realtimeとの差</th></tr>'
    for s in summaries:html_table+='<tr><td>'+html.escape(PROFILES[s['profile']]+' / '+LABELS[s['model']])+'</td>'+''.join(f'<td>{s[k]:.3f}秒</td>' for k in ['generation_median_seconds','dialogue_llm_translation_seconds','dialogue_bones_after_student_end_seconds','dialogue_gap_from_realtime_seconds'])+'</tr>'
    page='''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MoLingo / ReMoMask-2 / MoMask 実測</title><style>body{font-family:system-ui,sans-serif;margin:0;background:#edf1ed;color:#162b35}main{max-width:1300px;margin:auto;padding:30px}h1{font-size:28px}p{line-height:1.7}table{border-collapse:collapse;background:white;width:100%;font-variant-numeric:tabular-nums}td,th{padding:12px;border-bottom:1px solid #cedbd6;text-align:left}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:22px}article{background:white;padding:18px;border-radius:12px}video{width:100%;aspect-ratio:16/9;background:#162b35}a{color:#08745e}@media(max-width:500px){main{padding:12px}.grid{grid-template-columns:1fr}td,th{padding:6px;font-size:12px}}</style><main><h1>MoLingo / ReMoMask-2 / MoMask 実測比較</h1><p>原文をLLMで英訳して動作を生成。音声・字幕は原文のまま。3モデル × 2環境 × 共通5区間・音声会話の12本。研究室実機のRTX 5070では未測定です。</p><p><a href="README.md">条件と結果の説明</a> · <a href="summary.csv">集計CSV</a> · <a href="segment-times.csv">区間別CSV</a> · <a href="all-trials.csv">全90回CSV</a></p>'''+html_table+'</table><p>骨格中央値は常駐推論15回（英訳・通信・描画を除く）。会話は各条件1回で英訳・通信込み。動画は実測した待ち時間の再生です。MoMaskの一部出力には大きな体の傾きがあります。</p><div class="grid">'+''.join(cards)+'</div></main></html>'
    (root/'index.html').write_text(page)
    print(json.dumps({'cases':len(summaries),'trials':len(trials),'videos':len(videos)},ensure_ascii=False))


if __name__=='__main__':main()
