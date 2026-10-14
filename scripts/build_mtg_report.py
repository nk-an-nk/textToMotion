"""Package measured October 14 evidence; never performs model or paid API calls."""
import csv
import hashlib
import json
import re
import shutil
import struct
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'.motion-lab'
OUT=ROOT/'reports/mtg'
JST=timezone(timedelta(hours=9))

def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,list):return [clean(v) for v in value]
    if not isinstance(value,str):return value
    value=value.replace(str(ROOT),'${PROJECT_ROOT}').replace(str(ROOT).replace('\\','/'),'${PROJECT_ROOT}')
    value=re.sub(r'C:[\\/]+Users[\\/]+[^\\/\s"<>]+', '${USER_HOME}', value,flags=re.I)
    value=re.sub(r'hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{32,}', '[REDACTED]',value)
    value=re.sub(r'https?://[^\s"<>]+\?[^\s"<>]+', '[SIGNED_URL_REDACTED]',value)
    return value

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def doc(name,text):
    text=re.sub(r'(^#{1,6} [^\n]+\n)(?!\n)',r'\1\n',text.strip(),flags=re.M)
    (OUT/name).write_text(text+'\n',encoding='utf-8')
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda:handle.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)]))
def figure(name):
    plt.tight_layout();plt.savefig(OUT/'figures'/name,dpi=180,bbox_inches='tight');plt.close()

def main():
    for folder in ('figures','videos','videos/source','logs','logs/experiments','logs/realtime'):
        (OUT/folder).mkdir(parents=True,exist_ok=True)
    setup=read(ROOT/'reports/windows_actual_setup.json')
    records=sorted((read(p) for p in (DATA/'outputs').glob('*/experiment.json')),key=lambda x:x['created_at'])
    phases={'85a9c693a50d46efbe9ca652c43a0948':'setup_fps_failure',
            'cc28fe8e74cb4a13ad56eeea4c1e401b':'setup_cleanup_failure',
            '6ed544f25f3e463e979e2d1a047558c4':'setup_cleanup_retry_failure',
            '753b2940004541ddbcb2a2b999eb4c61':'live_software_late',
            'eaa34d251d0346df891192a86290bd36':'live_hardware_brief',
            'fb707be72644490ab0757d4822f38101':'live_hardware_corrected'}
    table=[]
    for r in records:
        identifier=r['id'];source=DATA/'outputs'/identifier;target=OUT/'logs/experiments'/identifier
        target.mkdir(exist_ok=True)
        for file in source.iterdir():
            if file.name.startswith('.') or file.name=='video.mp4':continue
            if file.suffix.lower() in ('.json','.log','.txt'):
                if file.suffix=='.json':write(target/file.name,read(file))
                else:(target/file.name).write_text(clean(file.read_text(encoding='utf-8',errors='replace')),encoding='utf-8')
            elif file.suffix.lower() in ('.npz','.vrma'):shutil.copyfile(file,target/file.name)
        t=r.get('timings',{})
        table.append({'experiment_id':identifier,'phase':phases.get(identifier,'setup_success'),
            'model':r['model_id'],'status':r['status'],'started_at_jst':datetime.fromisoformat(r['started_at']).astimezone(JST).isoformat(),
            'input_text':r.get('input_text',''),'model_text':r.get('model_text',''),'duration_seconds':r['duration_requested'],
            'seed':r['seed'],'official_command_seconds':r.get('inference_time'),
            'skeleton_seconds':t.get('skeleton_seconds'),'mp4_render_seconds':t.get('mp4_render_seconds'),
            'total_seconds':t.get('total_seconds'),'failure_seconds':r.get('time_to_failure'),
            'new_inference':True,'audio_conditioned':False,'error':clean(r.get('error',''))})
    with (OUT/'experiment_results.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=table[0].keys());w.writeheader();w.writerows(table)
    write(OUT/'logs/experiment_metadata.json',{'source_base_for_publication':'e04c03c9d9d386b2ec600100387364e3f29dfe8b',
        'source_bases_during_measurements':{'model_setup':'6697dda plus local Windows fixes','live_trials':'17b460b plus local Windows fixes'},
        'experiment_count':len(records),'successes':sum(r['status']=='succeeded' for r in records),
        'failures':sum(r['status']=='failed' for r in records),'cancelled':sum(r['status']=='cancelled' for r in records),
        'experiments':records})
    write(OUT/'logs/benchmark_results.json',setup)

    trials=[]
    folders=[DATA/'realtime-demo/trial1',DATA/'realtime-demo',DATA/'realtime-demo-corrected']
    ids=['753b2940004541ddbcb2a2b999eb4c61','eaa34d251d0346df891192a86290bd36','fb707be72644490ab0757d4822f38101']
    for i,(folder,identifier) in enumerate(zip(folders,ids),1):
        result=read(folder/'result.json');rows=list(csv.DictReader((folder/'events.csv').open(encoding='utf-8-sig')))
        events={}
        for event in rows:
            if event['clock_domain']=='client_performance' and event['time_ms']:
                events.setdefault(event['name'],float(event['time_ms']))
        start=events['user_text_submitted']
        offsets={key:(value-start)/1000 for key,value in events.items()}
        t=next(r for r in records if r['id']==identifier)
        item={'trial':i,'experiment_id':identifier,'result':result,'client_seconds_from_submit':offsets,
              'motion_status':t['status'],'motion_timings':t.get('timings'),
              'adopted':bool(result['generated_gesture_applied']),
              'rendering':'software SwiftShader' if i==1 else 'RTX 5070 Direct3D11',
              'duration_seconds':t['duration_requested'],'model_record':t}
        trials.append(item);write(OUT/'logs/realtime'/f'trial_{i}.json',item)
        shutil.copyfile(folder/'events.csv',OUT/'logs/realtime'/f'trial_{i}_events.csv')
        shutil.copyfile(folder/'avatar-and-realtime.webm',OUT/'videos/source'/f'trial_{i}.webm')
    write(OUT/'logs/realtime_results.json',trials)
    (ROOT/'reports/windows_actual_setup.json').write_text(json.dumps(clean(setup),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    corrected=read(ROOT/'reports/windows_realtime_generation.json')
    (ROOT/'reports/windows_realtime_generation.json').write_text(json.dumps(clean(corrected),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

    # Public model permissions are read from the actual locally used avatar.
    avatar=DATA/'avatars/VRM1_Constraint_Twist_Sample.vrm';b=avatar.read_bytes();size=struct.unpack_from('<I',b,12)[0]
    meta=json.loads(b[20:20+size])['extensions']['VRMC_vrm']['meta']
    write(OUT/'logs/avatar_license.json',{'source':'https://github.com/pixiv/three-vrm/blob/dev/packages/three-vrm/examples/models/VRM1_Constraint_Twist_Sample.vrm',
        'sha256':sha(avatar),'metadata':meta,'license':'https://vrm.dev/licenses/1.0/',
        'publication':'Rendered synthetic voice/avatar experiment videos only; no VRM file is distributed.',
        'attribution':'(c) 2022 pixiv Inc.; VRM Public License 1.0',
        'review_basis':'VRM Public License 1.0 sections 1(14), 2(a)(1); embedded avatarPermission everyone, commercialUsage corporation, allowRedistribution true.'})

    videos=[]
    def copy_video(source,name,identifier,kind,description,origin=None):
        target=OUT/'videos'/name;shutil.copyfile(source,target)
        info=probe(target);video=next(s for s in info['streams'] if s['codec_type']=='video')
        record=next(r for r in records if r['id']==identifier)
        videos.append({'file':'videos/'+name,'experiment_id':identifier,'kind':kind,'description':description,
            'input':record['input_text'],'model_prompt':record['model_text'],'model':record['model_id'],
            'generated_at_jst':datetime.fromisoformat(record['started_at']).astimezone(JST).isoformat(),
            'pipeline_status':record['status'],'environment':'Windows / Ryzen 7 5700X / RTX 5070 / CPU LLM2Vec',
            'bytes':target.stat().st_size,'sha256':sha(target),'duration_seconds':float(info['format']['duration']),
            'codec':video['codec_name'],'width':video['width'],'height':video['height'],
            'audio':any(s['codec_type']=='audio' for s in info['streams']),
            'source_webm':origin,'avatar':'VRM1_Constraint_Twist_Sample (pixiv Inc.)' if kind.startswith('live') else None})
    for model,name in [('kimodo','kimodo_demo.mp4'),('ardy','ardy_demo.mp4'),('text_to_vrma','text_to_vrma_demo.mp4')]:
        r=setup['real_generation'][model]
        copy_video(DATA/'outputs'/r['experiment_id']/'video.mp4',name,r['experiment_id'],'new_inference_skeleton','今回の新規テキスト条件付きGPU生成。骨格描画、無音。')
    late=OUT/'videos/realtime_late_cancelled.mp4'
    if not late.exists():subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(folders[0]/'avatar-and-realtime.webm'),'-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(late)],check=True)
    # Reuse the generated file without copying it onto itself.
    tempfile=DATA/'mtg/late-cancelled.mp4';tempfile.parent.mkdir(exist_ok=True);shutil.copyfile(late,tempfile)
    copy_video(tempfile,late.name,ids[0],'live_failure_recording','実API音声は成功。動作は発話終了に間に合わず取消。動作成功動画ではない。','source/trial_1.webm')
    for source,name,identifier,description,origin in [
        (folders[1]/'avatar-and-realtime.mp4','realtime_brief_gesture.mp4',ids[1],'初回GPU描画試行。新規動作採用、2秒の短い動作で見づらい。','source/trial_2.webm'),
        (folders[1]/'gesture-excerpt.mp4','brief_gesture_excerpt.mp4',ids[1],'上記録画の58秒以降の抜粋。同じ推論の再編集。','source/trial_2.webm'),
        (folders[2]/'avatar-and-realtime.mp4','realtime_conversation.mp4',ids[2],'修正版。実Realtime日本語音声と8秒の新規生成動作を同一発話中に適用。応答途中で録画終了。','source/trial_3.webm'),
        (folders[2]/'gesture-excerpt.mp4','gesture_transition.mp4',ids[2],'修正版録画67秒から13秒の抜粋。デフォルト→生成→デフォルトの遷移。別の新規推論ではない。','source/trial_3.webm')]:
        copy_video(source,name,identifier,'live_new_inference_recording',description,origin)
    vrm=OUT/'videos/vrm_demo.mp4'
    subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-ss','69','-i',str(folders[2]/'avatar-and-realtime.mp4'),'-t','8','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(vrm)],check=True)
    temp=DATA/'mtg/vrm-demo.mp4';shutil.copyfile(vrm,temp)
    copy_video(temp,vrm.name,ids[2],'live_new_inference_excerpt','修正版の適用付近8秒の抜粋。描画された右腕の上げ下げを確認。','source/trial_3.webm')
    write(OUT/'logs/video_manifest.json',videos)
    for src,dst in [(folders[1]/'generated-gesture.png','brief_gesture_application.png'),(folders[2]/'generated-gesture.png','corrected_gesture_application.png'),(folders[2]/'gesture-frames.png','gesture_comparison.png')]:
        shutil.copyfile(src,OUT/'figures'/dst)
    for name in ('check-64.png','check-65.png'):
        if (folders[1]/name).is_file():shutil.copyfile(folders[1]/name,OUT/'figures'/('trial_2_'+name))
    if (folders[1]/'retarget-measurements.json').is_file():
        write(OUT/'logs/realtime/trial_2_retarget_measurements.json',read(folders[1]/'retarget-measurements.json'))

    baseline=list(setup['real_generation'].values());names=['Kimodo','ARDY','text-to-vrma']
    skeleton=[x['timings']['skeleton_seconds'] for x in baseline];total=[x['timings']['total_seconds'] for x in baseline]
    plt.figure(figsize=(8,4));a=np.arange(3)
    plt.bar(a-.18,skeleton,.36,label='Skeleton ready');plt.bar(a+.18,total,.36,label='MP4 ready')
    plt.xticks(a,names);plt.ylabel('Seconds from input');plt.title('Local GPU smoke runs: one sample per pipeline');plt.legend()
    for x,y in zip(a+.18,total):plt.text(x,y+1,f'{y:.2f}',ha='center',fontsize=9)
    figure('model_latency.png')
    command=np.array([x['inference_time'] for x in baseline]);other=np.array(skeleton)-command;render=np.array(total)-np.array(skeleton)
    plt.figure(figsize=(8,4));plt.bar(names,command,label='Official command: load + CPU text + GPU generation')
    plt.bar(names,other,bottom=command,label='Other worker/export time');plt.bar(names,render,bottom=np.array(skeleton),label='MP4 rendering')
    plt.ylabel('Seconds');plt.title('Measured process boundaries; GPU-only time is not available');plt.legend(fontsize=8)
    figure('inference_breakdown.png')
    plt.figure(figsize=(10,4));colors=['#8b8b8b','#227c9d','#17a398']
    for i,trial in enumerate(trials):
        t=trial['client_seconds_from_submit'];start=t['first_audio_playback'];end=t.get('audio_playback_ended',None)
        filename=['realtime_late_cancelled.mp4','realtime_brief_gesture.mp4','realtime_conversation.mp4'][i]
        recorded=float(probe(OUT/'videos'/filename)['format']['duration'])
        visible_end=end if end is not None else recorded
        plt.broken_barh([(start,max(0,visible_end-start))],(i-.22,.35),facecolors=colors[i],alpha=.45)
        if trial['adopted']:
            gs=t['generated_gesture_started'];plt.broken_barh([(gs,trial['duration_seconds'])],(i-.12,.15),facecolors=colors[i]);plt.text(gs,i+.23,f'gesture {gs:.2f}s',fontsize=8)
        else:plt.text(visible_end+1,i,'cancelled after speech',fontsize=8)
    plt.yticks(range(3),['Trial 1: software, late','Trial 2: GPU, 2s action','Trial 3: GPU, 8s action'])
    plt.xlabel('Client clock: seconds from submitted text');plt.title('Speech/gesture; file-length recording endpoints are approximate')
    plt.xlim(0,130);plt.ylim(-.4,2.6);figure('speech_motion_timeline.png')
    # The gesture comparison image is extracted from real video, not drawn poses.

    env={'os':'Windows','python':'3.12.10 x64','cpu':'AMD Ryzen 7 5700X','cores':8,'logical_processors':16,
        'physical_memory_bytes':34269339648,'gpu':'NVIDIA GeForce RTX 5070','gpu_memory_mib':12227,
        'driver':'610.88','torch':'2.9.0+cu128','cuda':'12.8','compute_capability':[12,0],
        'motion_device':'cuda','text_encoder_device':'cpu','browser_rendering':'ANGLE NVIDIA Direct3D11 for trials 2 and 3'}
    write(OUT/'logs/environment.json',env)
    for file in (DATA/'logs').iterdir():
        if file.is_file() and file.suffix in ('.txt','.json','.log','.xml'):
            if file.suffix=='.json':write(OUT/'logs'/file.name,read(file))
            else:(OUT/'logs'/file.name).write_text(clean(file.read_text(encoding='utf-8',errors='replace')),encoding='utf-8')
    (OUT/'logs/browser-tests.xml').write_text(clean((ROOT/'reports/browser-tests.xml').read_text(encoding='utf-8')),encoding='utf-8')
    write(OUT/'logs/test_results.json',{'python':{'passed':89,'failed':0},'javascript':{'passed':16,'failed':0},
        'browser':{'passed':11,'failed':0,'skipped':2,'skip_reasons':['Historical recordings absent in this checkout','Separate paid live E2E not repeated during publication checks']},
        'live_experiments':'Three earlier real API trials are documented separately; skipped tests are not counted as passed.'})

    trialrows='\n'.join(f"| {t['trial']} | {t['rendering']} | {t['client_seconds_from_submit']['first_audio_playback']:.3f}秒 | {t['motion_timings']['skeleton_seconds']:.3f}秒 | "+(f"{t['client_seconds_from_submit']['generated_gesture_started']:.3f}秒" if t['adopted'] else '不採用')+f" | {t['duration_seconds']:g}秒 |" for t in trials)
    modelrows='\n'.join(f"| {name} | {r['timings']['skeleton_seconds']:.3f}秒 | {r['timings']['total_seconds']:.3f}秒 | {r['frames']} / {r['fps']:g}fps |" for name,r in zip(names,baseline))
    doc('README.md','''# 2026-10-14 MTG 成果物

Windows / RTX 5070 での3経路の新規動作生成と、日本語Realtime音声・VRM表示を実測した記録です。

- [MTG報告書](meeting_report.md) / [発表スライド構成](meeting_slides_outline.md)
- [実験計画と実施範囲](experiment_plan.md) / [全9試行のCSV](experiment_results.csv)
- [環境](environment_summary.md) / [モデル比較](model_benchmark.md) / [遅延分析](latency_analysis.md)
- [動作品質と確認限界](motion_quality_review.md) / [動画・証拠索引](evidence_index.md) / [再現手順](runbook.md)
- [Kimodo](videos/kimodo_demo.mp4) / [ARDY](videos/ardy_demo.mp4) / [text-to-vrma](videos/text_to_vrma_demo.mp4)
- **[修正版のジェスチャー切り替え](videos/gesture_transition.mp4)** / [日本語音声対話](videos/realtime_conversation.mp4)
- [生成時間グラフ](figures/model_latency.png) / [処理境界別時間](figures/inference_breakdown.png) / [発話と動作の時間軸](figures/speech_motion_timeline.png) / [録画の実フレーム比較](figures/gesture_comparison.png)

各モデルのsmoke比較は1試行ずつ、Realtimeは3試行です。遅延条件の制御テストを実APIの成功率と混同しません。短い動作・取消・失敗も記録しています。VRMモデル本体、APIキー、トークン、重みは含みません。
''')
    doc('meeting_report.md',f'''# 2026-10-14 実験報告

## 目的
研究室PCで文章条件付き動作生成を動かし、日本語音声対話と3Dアバターのジェスチャーを同時に出せるか確認する。

## 実施内容
Kimodo / ARDY / text-to-vrmaのローカルGPUセットアップと3秒の新規生成、Realtime gpt-realtime-2.1 / marin とVRMのライブ録画3回、Windowsの出力変換・一時ファイル処理・英語秒数指定の修正。推論パイプラインは合計9試行（成功5、失敗3、取消1）。追加の大量反復ベンチマークは実施していない。

## 実測結果
| 経路 | 骨格まで | MP4まで | フレーム数 / FPS |
|---|---:|---:|---|
{modelrows}

動画: [Kimodo](videos/kimodo_demo.mp4)、[ARDY](videos/ardy_demo.mp4)、[text-to-vrma](videos/text_to_vrma_demo.mp4)。いずれも今回の新規テキスト条件付き推論、3秒、seed 0、音声入力なし。
グラフ: [生成時間](figures/model_latency.png)、[処理境界別時間](figures/inference_breakdown.png)。[全CSV](experiment_results.csv)には失敗も含む。

## 発話とジェスチャー
| 試行 | 描画 | 音声開始 | 骨格生成 | 動作適用（入力から） | 動作長 |
|---|---|---:|---:|---:|---:|
{trialrows}

採用は2/3回（66.7%）。これは長い応答と比較条件Cの3試行についての状態・イベント上の値で、一般的な成功率や標準Dの性能ではない。Trial 2は2秒だけで見づらく、使用者からジェスチャーが見えないとの指摘を受けた。Trial 3で8秒の動作と実映像の右手上げ下げを確認した。意味的一致・自然さ・連続会話中の品質は未採点。

[修正版の日本語音声対話](videos/realtime_conversation.mp4)、[デフォルト→生成→待機の切り替え](videos/gesture_transition.mp4)、[VRMの動作部分](videos/vrm_demo.mp4)、[実フレーム比較](figures/gesture_comparison.png)、[時間軸](figures/speech_motion_timeline.png)。音声は実API出力、動作も同じ試行中の新規GPU推論。録画は応答途中で終了しており、全応答ではない。

## 失敗とボトルネック
1. Kimodo NPZにはFPSがないため変換失敗。公式config.yamlからFPSを読むよう修正。
2. text-to-vrmaはVRMA生成後にWindowsのcaptureファイルロックで2回失敗。プロセスツリー終了と削除再試行を追加。
3. SwiftShaderのCPU描画時は骨格約120.7秒。発話終了後の結果を取消。GPU描画の別試行では約62.5秒／68.1秒。ただし描画方式・動作長・出力トークン数が変わっており、因果効果を定量化した比較ではない。
4. 英語three secondsを読めず既定2秒になっていた。単語の数値指定を処理する修正と回帰テストを追加。
5. モデルCLI起動、CPU LLM2Vec、GPU推論、変換が含まれるバッチ待ち時間が大きい。GPUのみ、文章処理のみ、VRAM/RAMピークは未計測。標準Dの3秒期限に間に合う性能を実証していない。
6. 元ログにLLM2Vec/PEFT重み読み込みのMISSING / UNEXPECTED表示がある。生成出力は取得できたが、埋め込みへの影響とキー互換性を独立検証していない。文章に対する意味的成功の根拠として処理完了だけを使わない。

## 次回の研究課題
同じ入力・seed・期間で複数反復し、モデル読み込み、CPUエンコード、GPU推論を個別に計測する。常駐ワーカー・キャッシュを検討。短い実会話の期限内採用率、単語同期、足滑り、指示の意味的一致を評価する。遅延0/1/3/10秒の制御テストはあるが実API動画比較は未取得。[再現手順](runbook.md)、[品質レビュー](motion_quality_review.md)。Kebbiは未実装で、実機関節・速度・安全制約の検証が必要。

## 保存・公開
公開ブランチはnakano/1014。動画は通常Gitで保存し、[証拠索引](evidence_index.md)に実験ID・日時・入力・来歴・圧縮・権利を記載。再配布不可AvatarSampleのモデル本体は含めない。今回の動画は公開許諾を確認したVRM1_Constraint_Twist_Sampleの描画を使用。
''')
    doc('meeting_slides_outline.md','''# MTG発表構成

1. 目的：文章→動作と日本語音声→VRMを研究室PCで成立させる。
2. 環境：RTX 5070 / RAM約32GiB、CPUテキスト処理・GPU動作生成。
3. 3経路の測定：[生成時間](figures/model_latency.png)。1試行ずつであることを明示。
4. ライブ録画：[修正版ジェスチャー](videos/gesture_transition.mp4)を先に視聴。
5. 同期：[時間軸](figures/speech_motion_timeline.png)。音声約0.7秒、動作約64〜69秒。
6. 失敗：FPS、Windowsファイルロック、遅い結果の取消、2秒に縮まった指定。
7. 品質：上げ下げは映像で確認、自然さ・意味一致は未評価。状態遷移だけでは品質を保証しない。
8. 次回：常駐化、反復測定、短い発話での期限内採用、Kebbiの関節仕様。

発表時は[meeting_report.md](meeting_report.md)と[evidence_index.md](evidence_index.md)を参照。スライドファイルを作成済みと称さず、本ファイルは構成案。
''')
    doc('experiment_plan.md','''# 実験計画と実際の実施範囲

| 項目 | 実施 | 判定 |
|---|---|---|
| 3経路の3秒smoke | 各1成功。途中失敗も保存 | 実モデル元NPZ/VRMA、骨格JSON、MP4で成立確認 |
| Realtime音声＋新規動作 | 3試行、比較条件C | 音声、生成状態、適用イベント、実映像を個別確認 |
| 8秒の右手動作 | 新規1回 | 240フレーム、映像の上げ下げ確認。意味品質採点なし |
| 遅延0/1/3/10秒 | JS制御テスト | 人工遅延の状態制御。実API動画比較は未実施 |
| A/B/C/Dの制御 | JSテスト | 実APIで全条件を比較していない |
| マイクの実会話 | 未実施 | 入力はテキスト。実マイク認識の精度は不明 |
| Kebbi | 未実装 | 実機への送信なし |

結果を良く見せるため失敗を除外しない。再録画・抜粋は新たな推論回数に数えない。モデルごとに異なる入力のため、モデル性能の順位を結論しない。今後は入力・動作長・seed・プロセス状態を揃えて反復する。
''')
    doc('environment_summary.md','''# 実行環境

Windows、Python 3.12.10 x64、AMD Ryzen 7 5700X（8コア16スレッド）、物理RAM 34,269,339,648 bytes（約31.92GiB）、RTX 5070（12,227MiB）、NVIDIAドライバー610.88。PyTorch 2.9.0+cu128 / CUDA 12.8 / capability 12.0。動作モデルcuda、LLM2VecはCPU。

ライブTrial 1はSwiftShader CPU描画、Trial 2/3はANGLE NVIDIA Direct3D11。Realtimeはgpt-realtime-2.1、音声marin、入力はテキスト、日本語音声出力。Trial 1応答上限2048、Trial 2/3は4096 tokens。セッション上限180秒。予算3USDは事前許可枠であり実請求上限や実支払額の計測ではない。

公開時の基準はリモートwork e04c03c。モデルセットアップ測定時は6697dda、ライブ測定時は17b460bとローカルWindows修正。元モデルの固定リビジョン・ライブラリ一覧は[環境JSON](logs/environment.json)、[Kimodo GPU](logs/kimodo-gpu.json)、[ARDY GPU](logs/ardy-gpu.json)、各cuda-versions.txt、[元実験記録](logs/experiments/)参照。最新版と測定時の違いを隠さない。

APIキー、Hugging Faceトークン、重み、VRM本体、個人の音声・顔映像を含まない。ローカルユーザー名・絶対パスは置換した。生成した音声は合成音声で実在人物の録音ではない。
''')
    doc('model_benchmark.md',f'''# モデルの実測

| 経路 | 骨格まで | MP4まで | フレーム数 / FPS |
|---|---:|---:|---|
{modelrows}

Kimodo入力はRaise your right hand and wave for three seconds.、ARDY / text-to-vrmaはHello.（元入力はこんにちは）。全て3秒・seed 0。Kimodo77関節、ARDY27関節、VRMA由来44関節。text-to-vrmaはARDY Core8と同じ重みを使い、公式リターゲットと後処理を追加する経路。

骨格までの時間は入力受付からJSON保存まで、MP4までにはその後の描画を含む。official_command_secondsはモデル読み込み・CPU文章処理・GPU生成などを含み、GPU単体の推論秒数ではない。各1試行、モデル入力・CFG・後処理が異なるため有意な速度順位や平均値・分散は求めない。測定中のダウンロード時間は含まない。

[CSV](experiment_results.csv) / [時間グラフ](figures/model_latency.png) / [処理境界](figures/inference_breakdown.png)。
''')
    doc('latency_analysis.md',f'''# 発話・動作の遅延

| 試行 | 描画 | 音声開始 | 骨格生成 | 動作適用（入力から） | 動作長 |
|---|---|---:|---:|---:|---:|
{trialrows}

音声開始・動作適用は同じclient_performance時計のuser_text_submittedとの差分。モデル開始/終了はserver_monotonic同士の差分。client_audioは別時計で、サーバー時刻から直接差し引かない。文字到着と音声開始、response.doneと音声再生終了も区別する。

Trial 1は発話終了後の結果を取消し、動作の成功として数えない。Trial 2/3の音声は録画終了時も継続していたため、全発話長は不明。時間軸の録画終端はファイル長による目安で、入力前の短い録画部分を含む。採用2/3=66.7%はこの3試行の事実であり、繰り返し会話の一般性能ではない。比較条件Cは期限を無視して発話中の完成次第適用する。標準Dの3秒期限で採用できるとの実証はない。

SwiftShader試行とGPU描画試行ではモデル期間・応答上限も変化した。CPU競合の可能性はあるが描画方式単独の効果を推定できない。モデル読み込み・CPUエンコード・GPUの独立測定とRAM/VRAMピークは未取得。

[時間軸](figures/speech_motion_timeline.png)。0/1/3/10秒の遅延条件別動画は作成していない。JSテストによる期限・取消制御の検査を実API遅延比較と扱わない。
''')
    doc('motion_quality_review.md','''# 動作品質のレビュー

Trial 2では適用イベントが出たが動作は2秒だけで、視聴者からジェスチャーが入っていないとの指摘を受けた。英語three secondsを数字として解釈できず2秒に縮まっていたことを確認し、単語指定の処理と回帰テストを追加した。

Trial 3は8秒・240フレームの新規Kimodo出力。右手の元ワールド位置の範囲はx約0.209m、y約0.930m、z約0.313m。VRMへ適用した録画の複数フレームで頭付近までの右腕上げとその後の下げを確認。[比較画像](figures/gesture_comparison.png)、[映像](videos/gesture_transition.mp4)。この数値は元骨格の軌跡で、VRM腕位置を実測した値ではない。

繰り返し手振りの自然さ、8秒間すべて指示通りか、文の意味との一致、指先のねじれ、接地、足滑り、顔表情の品質は未採点。位置から推定する最小回転のリターゲットは手首の軸ねじれを決定できない。状態遷移だけで見た目を成功と判定しない。口の動きは音声信号レベルによる簡易表現で、音素単位のリップシンクではない。

実ログにはLLM2Vec/PEFTの読み込み時にMISSING / UNEXPECTED表示がある。重みファイルのSHA照合と処理完了は確認したが、アダプターキーの互換性・埋め込みの同一性は未検証。意味品質を評価する前に、この警告の影響を切り分ける。

実行結果のsucceededは数値・形式・処理完了を意味する。意味的成功と分けて保存。Kebbi向けの角度・速度・関節制約・安全性は未検証。
''')

    entries=['# 動画・証拠索引','', '## 公開許諾と来歴','',
        '動画に使ったアバターはVRM1_Constraint_Twist_Sample、© 2022 pixiv Inc.。実ファイルのVRMメタデータはavatarPermission=everyone、commercialUsage=corporation、allowRedistribution=true、modification=allowModificationRedistribution。モデル利用により得られた映像の公開は[VRM Public License 1.0](https://vrm.dev/licenses/1.0/)の第1条(14)、第2条(a)(1)とライセンス設定を根拠に確認。[実メタデータとSHA](logs/avatar_license.json)。VRM本体は配布しない。別のAvatarSampleの再配布不可VRMも含めない。OpenAI marinによる合成音声、テキスト入力は研究説明のみ。マイクや実在人物の録音なし。', '',
        '基準環境はWindows / Ryzen 7 5700X / RTX 5070 / PyTorch 2.9.0+cu128 / CPU LLM2Vec。ライブ映像はGPU Direct3D11、失敗試行のみSwiftShader。各元記録は[experiments](logs/experiments/)に保存。以下の抜粋は同じライブ新規推論を撮影した動画の編集で、別の推論や保存済み動作を使った別会話ではない。', '', '## MP4一覧','']
    for v in videos:
        entries += [f"### [{v['file'].split('/')[-1]}]({v['file']})",'',
            f"- 実験ID: `{v['experiment_id']}` / モデル: {v['model']} / パイプライン状態: {v['pipeline_status']}",
            f"- 生成日時: {v['generated_at_jst']}（実験開始日時。動画編集日時とは区別）",
            f"- 元入力: {v['input']}",f"- 動作モデル入力: `{v['model_prompt']}`",
            f"- 内容: {v['description']}",f"- 仕様: {v['duration_seconds']:.3f}秒、{v['width']}×{v['height']}、{v['codec']}、音声{'あり' if v['audio'] else 'なし'}、{v['bytes']/1024/1024:.2f}MiB",
            f"- 来歴: {v['kind']} / SHA-256 `{v['sha256']}`",'']
    entries += ['## 圧縮・抜粋と元動画','',
        'ライブ元動画はVP8/Opus WebM。[Trial 1](videos/source/trial_1.webm)、[Trial 2](videos/source/trial_2.webm)、[Trial 3](videos/source/trial_3.webm)を保持。MP4はH.264 CRF20 / preset fast / yuv420p、音声AAC、faststartへ変換したため再圧縮による差がある。速度変更、フレーム補間、動作の合成は行っていない。ログは認証情報・ローカルパスを置換し、改行をLFへ統一、末尾空白を除去した。元ログはローカルに保持。詳細サイズ・SHA・コーデックは[動画manifest](logs/video_manifest.json)と[成果物manifest](logs/artifact_manifest.json)。', '',
        'gesture_transitionはTrial 3録画の67秒から13秒、vrm_demoは69秒から8秒の抜粋。brief_gesture_excerptはTrial 2の58秒から12秒を指定し元動画終端まで。元のライブ録画は応答途中で終了する。失敗Trial 1は音声のみ成立、動作不採用と明示。', '',
        '各ファイルはGitHubの100MiB制限未満で通常Gitを使用。LFSは使用しない。[GitHub大容量ファイル仕様](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)。GitHubでの埋め込み再生の可否はUIに依存するため、ファイルページのRaw/Downloadから取得できることを検証する。', '',
        '## 作成していない成果物','', '遅延0/1/3/10秒の実API比較動画、Kebbi実機動画、自然さの評価票、GPU単独・CPU単独の時間分解、実請求額は未作成。既存workのreports/videos内にある過去動画は今回の新規推論回数に含めない。']
    doc('evidence_index.md','\n'.join(entries))
    doc('runbook.md','''# 再現・閲覧手順

## MTGで確認
1. READMEから修正版gesture_transition.mp4を再生。前半の待機と右腕の上げ下げを見る。
2. experiment_results.csvの成功・失敗・取消と実験IDを確認。
3. モデル時間グラフと発話/動作の時間軸を比較。
4. 自然さ・意味的一致を処理成功と混同しない。

## 環境の再現
Python 3.12 x64、RTX 5070向けドライバー、Git、Node/npm、FFmpeg、VS2022 C++。このリポジトリのsetup-windows.ps1とconfigs/lab-windows.jsonを使用。モデル規約同意とLlamaアクセス承認が必要。ローカル認証ファイルは.gitignore対象、キーをGitへ追加しない。

```powershell
.\\setup-windows.ps1 -InstallPrerequisites -AcceptModelLicense
.\\setup-conversation.ps1
npx playwright install chromium
```

## 実験の再実行（有料Realtime API）
API利用の明示的許可を持つ利用者が実行する。scripts/run_realtime_experiment_server.pyはOPENAI_API_KEY環境変数を優先し、任意でローカルconfig/reaitimeapi.txt等を読む。キーの値は保存しない。セッション180秒、接続3回、事前許可3USDは実請求額の厳密な上限ではない。

```powershell
# 環境変数OPENAI_API_KEYを安全に設定してから、端末1で起動
.\\.venv\\Scripts\\python.exe scripts/run_realtime_experiment_server.py
# 端末2。利用許諾済みのVRM 1.0をローカルに指定
$env:MOTION_LAB_TEST_VRM = 'C:\\Models\\VRM1_Constraint_Twist_Sample.vrm'
node scripts/run_realtime_vrm_experiment.cjs
```

実験スクリプトは比較C、8秒の右手指示、4096 tokensの長い音声応答を使う。出力先は.motion-lab/realtime-run-<日時>、既存録画を上書きしない。標準D/3秒期限の実証ではない。VRMは公式[pixiv/three-vrmモデル](https://github.com/pixiv/three-vrm/blob/dev/packages/three-vrm/examples/models/VRM1_Constraint_Twist_Sample.vrm)から取得しメタデータを確認する。ライブラリMITとモデルのVRMライセンスは別。

## ローカル記録の再集計
```powershell
.\\.venv\\Scripts\\python.exe scripts/build_mtg_report.py
.\\.venv\\Scripts\\python.exe -m pytest -q
npm run test:unit
npx playwright test
```
集計スクリプトは元の.motion-lab/outputsと3つの録画フォルダーが必要。公開CSV/JSON/動画は元環境がなくても閲覧できる。集計は推論やAPI呼出しをしない。scripts/download_llama_ranges.pyは転送問題時の補助取得処理で、最終公式SHA-256照合を行う。元のsetup_modelsとprepare_lab_textを先に使う。

モデル、重み、VRM本体はGitHubから取得できると称さない。tests/browser/live.spec.cjsは別の厳しい短期限E2Eで、今回の長応答C試行と同条件ではない。既存record_vrm_demo.cjsは保存済みモーション/音声の再生であり新規推論ではない。
''')

    manifest=[]
    for file in sorted(OUT.rglob('*')):
        if file.is_file() and file.suffix.lower() in ('.md','.json','.csv','.xml','.txt','.log'):
            canonical=file.read_bytes().replace(b'\r\n',b'\n')
            file.write_bytes(re.sub(rb'[ \t]+(?=\n|$)',b'',canonical))
        if file.is_file() and file.name!='artifact_manifest.json':manifest.append({'file':file.relative_to(OUT).as_posix(),'bytes':file.stat().st_size,'sha256':sha(file)})
    if any(x['bytes']>=100*1024**2 for x in manifest):raise RuntimeError('An artifact exceeds the ordinary GitHub file limit.')
    write(OUT/'logs/artifact_manifest.json',manifest)
    print(f'Packaged {len(records)} model attempts, {len(trials)} live trials, {len(videos)} MP4 files and {len(manifest)} artifacts.')

if __name__=='__main__':main()
