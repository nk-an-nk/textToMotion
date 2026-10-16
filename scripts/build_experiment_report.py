#!/usr/bin/env python3
"""Build the Japanese experiment report from existing, public experiment records.

This script never starts a GPU or calls a paid inference API. Run from repo root.
Requires python-pptx and Pillow. PDF export is a separate LibreOffice command.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import shutil
import statistics
import subprocess
import zipfile
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.xmlchemy import OxmlElement
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/presentation-20261016'
OLD = ROOT / 'reports/model-comparison/runpod-20261014'
B300 = ROOT / 'reports/kimodo-b300-20261015'
OUT.mkdir(parents=True, exist_ok=True)
FONT = 'Noto Sans CJK JP'
NAVY, INK, MUTED = '122B3A', '183440', '5B707B'
TEAL, BLUE, GOLD, RED = '007F80', '3269AC', 'B56B13', 'B84642'
PALE, LINE, WHITE = 'F0F5F5', 'DCE6E8', 'FFFFFF'
NAMES = {'kimodo':'Kimodo', 'ardy':'ARDY', 'motionlcm':'MotionLCM',
         'momask':'MoMask', 'mmm':'MMM', 'reactmotion':'ReactMotion', 'maai':'MaAI'}
MODELS = list(NAMES)
REPO = 'https://github.com/nk-an-nk/textToMotion/blob/work/'


def read(path):
    return json.loads(Path(path).read_text())


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def prepare_media():
    """Copy existing public movies and extract poster frames without inference."""
    (OUT/'media').mkdir(exist_ok=True)
    (OUT/'assets').mkdir(exist_ok=True)
    entries=[]
    for model in MODELS:
        for group,filename in [('dialogue','demo.mp4'),('common','combined.mp4')]:
            src=OLD/('audio-input-dialogue' if group=='dialogue' else 'common')/model/filename
            dst=OUT/'media'/f'{group}-{model}.mp4'
            shutil.copy2(src,dst)
            entries.append(dict(id=f'{group}-{model}',name=NAMES[model],group=group,
                                path=str(dst.relative_to(OUT)),source=str(src.relative_to(ROOT))))
            poster=OUT/'assets'/f'{group}-{model}.png'
            if not poster.exists():
                if group=='dialogue':
                    receipt=read(src.parent/'measurement.json')
                    t=1.9+receipt['bone_ready_observed_seconds_after_student_end']+1.1
                else:
                    t=5.8
                subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss',str(t),
                                '-i',str(src),'-frames:v','1','-update','1','-y',str(poster)],check=True)
    for mode in ['fp32-100','tf32-20']:
        src=B300/f'video-{mode}/demo.mp4';dst=OUT/'media'/f'b300-{mode}.mp4'
        shutil.copy2(src,dst);shutil.copy2(src.parent/'preview.png',OUT/'assets'/f'b300-{mode}.png')
        entries.append(dict(id=f'b300-{mode}',name=f'Kimodo B300 {mode}',group='b300',
                            path=str(dst.relative_to(OUT)),source=str(src.relative_to(ROOT))))
    for name in ['english-lesson','english-lesson-ardy']:
        src=ROOT/'reports/segmented'/name/'combined.mp4';dst=OUT/'media'/f'segmented-{name}.mp4'
        shutil.copy2(src,dst)
        poster=OUT/'assets'/f'segmented-{name}.png'
        if not poster.exists():
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-ss','5.8',
                            '-i',str(src),'-frames:v','1','-update','1','-y',str(poster)],check=True)
        entries.append(dict(id=f'segmented-{name}',name=name,group='segmented',
                            path=str(dst.relative_to(OUT)),source=str(src.relative_to(ROOT))))
    (OUT/'media-index.json').write_text(json.dumps(entries,ensure_ascii=False,indent=2)+'\n')


prepare_media()


common = {r['model']:r for r in read_csv(OLD/'common-input-times.csv')}
audio = {r['model']:r for r in read_csv(OLD/'audio-response-times.csv')}
benchmark = read(B300/'benchmark/summary.json')
live = {m:read(B300/f'dialogue-{m}/measurement.json') for m in ['fp32-100','tf32-20']}
warm = {}
for model in ['motionlcm','mmm','momask']:
    records = [read(OLD/f'common/{model}/segments/{i:02d}/motion-generation.json') for i in range(1,6)]
    vals = [r['skeleton_seconds'] for r in records[1:]]
    warm[model] = dict(first=records[0]['skeleton_seconds'], median=statistics.median(vals),
                       minimum=min(vals), maximum=max(vals), frames=[r['native_frames'] for r in records])

costs = {}
for mode, m in live.items():
    inp, out = m['usage']['input_token_details'], m['usage']['output_token_details']
    realtime_usd = (inp['text_tokens']*4 + inp['audio_tokens']*32 + out['text_tokens']*24 + out['audio_tokens']*64)/1e6
    input_duration = m['first_teacher_audio_seconds_after_input_start'] - m['first_teacher_audio_seconds_after_student_end']
    window = input_duration + m['bone_ready_observed_seconds_after_student_end']
    gpu_yen = window * 8.99/3600*200
    costs[mode] = dict(gpu_usd_per_hour=8.99, jpy_per_usd=200,
                       request_window_seconds=window, gpu_yen=gpu_yen,
                       realtime_usage_estimate_usd=realtime_usd, realtime_yen=realtime_usd*200,
                       subtotal_yen=gpu_yen+realtime_usd*200,
                       excluded=['transcription','startup','idle time','storage','video export'],
                       actual_invoice_usd=None)

data = {'date_jst':'2026-10-16','common_five_sentences':common,'audio_input_comparison':audio,
        'warm_four_distinct_segments':warm,'b300_native_benchmark':benchmark,
        'b300_live':live,'b300_cost_estimates':costs,
        'pricing_source':'https://developers.openai.com/api/docs/models/gpt-realtime-2.1',
        'pricing_verified_date':'2026-10-15',
        'pricing_usd_per_million':{'text_input':4,'text_output':24,'audio_input':32,'audio_output':64}}
(OUT/'measurements.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333333), Inches(7.5)
prs.core_properties.title = '音声対話 × Text-to-Motion × VRM — 実験報告'
prs.core_properties.subject = '7モデル比較・Kimodo B300検証・応答遅延・費用・研究室PCへの展開'
prs.core_properties.author = 'textToMotion experiment report'
outline = []
embedded_videos = []


def rgb(value):
    return RGBColor.from_string(value)


def box(s, x, y, w, h, fill=PALE, line=None, radius=False):
    shape = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
                               Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid(); shape.fill.fore_color.rgb = rgb(fill)
    if line:
        shape.line.color.rgb = rgb(line)
    else:
        shape.line.fill.background()
    if radius:
        shape.adjustments[0] = .12
    # Keep the diagrams flat instead of inheriting the template's shadow effect.
    shape._element.spPr.append(OxmlElement('a:effectLst'))
    return shape


def text(s, x, y, w, h, value, size=20, color=INK, bold=False,
         align=PP_ALIGN.LEFT, margin=0, valign=MSO_ANCHOR.TOP, link=None):
    shape = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = shape.text_frame; tf.clear(); tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(margin)
    tf.margin_top = tf.margin_bottom = Inches(margin)
    tf.vertical_anchor = valign
    for i, line in enumerate(str(value).split('\n')):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align; p.space_after = Pt(5); p.line_spacing = 1.14
        r = p.add_run(); r.text = line
        r.font.name = FONT; r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = rgb(color)
        props = r._r.get_or_add_rPr()
        props.set('lang','ja-JP')
        ea = OxmlElement('a:ea'); ea.set('typeface',FONT); props.append(ea)
        if link:
            r.hyperlink.address = link
    return shape


def picture(s, path, x, y, w, h, crop=None, link=None):
    im = Image.open(path)
    left, top, right, bottom = crop or (0,0,1,1)
    iw, ih = im.width*(right-left), im.height*(bottom-top)
    if iw/ih > w/h:
        desired = ih*w/h/im.width
        delta = (right-left-desired)/2; left += delta; right -= delta
    else:
        desired = iw*h/w/im.height
        delta = (bottom-top-desired)/2; top += delta; bottom -= delta
    p = s.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
    p.crop_left, p.crop_top, p.crop_right, p.crop_bottom = left, top, 1-right, 1-bottom
    if link:
        p.click_action.hyperlink.address = link
    return p


def movie(s, media_id, x, y, w, h):
    """Embed the complete MP4, plus a static PDF-compatible poster."""
    poster=OUT/'assets'/f'{media_id}.png'
    path=OUT/'media'/f'{media_id}.mp4'
    picture(s,poster,x,y,w,h)
    shape=s.shapes.add_movie(str(path),Inches(x),Inches(y),Inches(w),Inches(h),
                             poster_frame_image=str(poster),mime_type='video/mp4')
    embedded_videos.append({'id':media_id,'slide':len(prs.slides),
                            'path':str(path.relative_to(OUT)),
                            'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    return shape


def slide(title, subtitle='', source='', notes='', section='実験報告', dark=False):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid(); s.background.fill.fore_color.rgb = rgb(NAVY if dark else WHITE)
    color = WHITE if dark else INK
    box(s,.48,.40,.08,.35,TEAL)
    text(s,.7,.35,11.9,.32,section,size=10,color='AFC9CE' if dark else TEAL,bold=True)
    text(s,.67,.94,12,.64,title,size=29,color=color,bold=True)
    if subtitle:
        text(s,.69,1.65,11.95,.55,subtitle,size=14,color='C2D5DA' if dark else MUTED)
    box(s,.67,7.03,12,.012,'355160' if dark else LINE)
    text(s,.7,7.12,10.9,.22,source or 'textToMotion / 実験記録 2026-10-13〜15（UTC記録）',size=8,color='BED1D6' if dark else MUTED)
    text(s,12.0,7.08,.55,.30,f'{len(prs.slides):02d}',size=11,color='C2D5DA' if dark else MUTED,align=PP_ALIGN.RIGHT)
    s.notes_slide.notes_text_frame.text = title+'\n\n'+notes+'\n\n出典: '+source
    outline.append({'slide':len(prs.slides),'title':title,'subtitle':subtitle,'notes':notes,'source':source})
    return s


def table(s, x, y, widths, headers, rows, row_h=.49, font=15, highlights=()):
    w = sum(widths)
    box(s,x,y,w,row_h,NAVY)
    px = x
    for hd,cw in zip(headers,widths):
        text(s,px+.12,y+.09,cw-.20,row_h-.12,hd,size=font-1,color=WHITE,bold=True)
        px += cw
    for i,row in enumerate(rows):
        yy = y+(i+1)*row_h
        box(s,x,yy,w,row_h,'E6F3F1' if i in highlights else (PALE if i%2==0 else WHITE))
        px=x
        for j,(value,cw) in enumerate(zip(row,widths)):
            text(s,px+.12,yy+.09,cw-.20,row_h-.12,value,size=font,
                 color=TEAL if i in highlights else INK,bold=(j==0 or i in highlights))
            px += cw


def callout(s, x, y, w, h, title, body, fill=PALE, accent=TEAL, body_size=17):
    box(s,x,y,w,h,fill,radius=True);box(s,x,y,.045,h,accent)
    text(s,x+.20,y+.18,w-.38,.45,title,size=18,color=accent,bold=True)
    if body:
        text(s,x+.20,y+.78,w-.40,h-.86,body,size=body_size)


def metric(s,x,y,w,value,label,note,color=TEAL):
    box(s,x,y,w,2.35,PALE,radius=True)
    text(s,x+.2,y+.14,w-.4,.42,label,size=16,color=MUTED,bold=True)
    text(s,x+.2,y+.73,w-.4,.83,value,size=40,color=color,bold=True)
    text(s,x+.2,y+1.72,w-.4,.48,note,size=13,color=MUTED)


def bar(s, label, value, maximum, x, y, w=7.5, color=TEAL, suffix='秒', fmt='.3f'):
    text(s,.95,y,x-1.15,.54,label,size=19,bold=True)
    box(s,x,y+.03,w,.35,PALE)
    box(s,x,y+.03,max(.025,w*value/maximum),.35,color)
    text(s,x+w+.18,y-.01,1.60,.50,format(value,fmt)+suffix,size=21,color=color,bold=True)


# 01 — cover
s=slide('音声対話 × Text-to-Motion × VRM', '生成速度・会話の応答遅延・費用・研究室PCでの実行を検証',
        '報告日 2026-10-16（日本時間） / nk-an-nk/textToMotion / work',
        '既存の実推論・音声入力・動画・CSVを再集計した報告。追加のGPU課金やモデル推論は実施していない。実験日の原記録はUTC、報告日は日本時間。', dark=True)
text(s,.78,2.7,7.3,1.7,'7モデルの比較と\nKimodo / B300の検証結果',size=34,color=WHITE,bold=True)
text(s,.8,4.76,6.65,1.1,'目標：生徒の音声を受け取り、\n先生の発話と上半身ジェスチャーを自然なテンポで返す',size=20,color='C2D5DA')
picture(s,OUT/'assets/b300-tf32-20.png',8.45,2.38,3.9,4.35,crop=(.34,.15,.69,.805))
text(s,.8,6.32,6.8,.32,'本編18枚 ＋ 付録12枚 / 全18本のデモ動画をスライド内に収録',size=12,color='AFC9CE')

# 02 — principal findings
s=slide('生成単体の高速化は確認。会話の待ち時間には課題が残る',
        '「生成が速い」と「会話の返答が速い」を分けて評価する',
        '[R1] common/*/motion-generation.json  [R3] benchmark/summary.json  [R4] dialogue-times.csv',
        'MotionLCMはRTX4090で初回を除く4つの異なる区間の中央値。Kimodoの0.435秒はB300、149フレーム、3反復の中央値。3.252秒は別の実音声入力会話1回の値であり、同じ統計量や実行条件ではない。')
metric(s,.76,2.5,3.82,'0.039秒','MotionLCM / RTX 4090','初回を除く4区間の生成処理中央値')
metric(s,4.76,2.5,3.82,'0.435秒','Kimodo / B300・20 steps','約5秒の動作、3反復の中央値')
metric(s,8.76,2.5,3.82,'3.252秒','Realtimeとの差','B300高速設定の会話実測・1回',color=GOLD)
callout(s,.76,5.24,11.82,1.28,'判断','次の焦点はモデル常駐・全文待ち・結果中継の短縮と、ジェスチャー品質の評価。',body_size=18)

# 03 — target and flow
s=slide('目標は、音声の返答と上半身ジェスチャーをそろえること',
        '評価対象：録音した生徒音声 → Realtimeの実応答 → 新規の動作生成 → VRM表示',
        '[R2] audio-response-times.csv  [R4] dialogue-*/measurement.json',
        '学生は録音済み合成音声を実時間で送信。生マイクの連続会話や自由回答の試験ではない。基準時刻は生徒の発話終了。教師の全文を受信してから動作を生成し、教師音声は骨格受信まで保留する。')
steps=[('生徒の音声','先生、こんにちは！'),('Realtime','返答の音声・文字'),('動作モデル','新規の骨格を生成'),('VRMアバター','発話と動作を同期')]
for i,(title,body) in enumerate(steps):
    x=.76+i*3.02
    box(s,x,2.65,2.72,1.5,PALE,radius=True)
    text(s,x+.16,2.85,2.40,.44,title,size=21,bold=True,color=TEAL)
    text(s,x+.16,3.5,2.4,.40,body,size=15)
    if i<3:text(s,x+2.76,3.10,.25,.4,'→',size=20,color=MUTED)
callout(s,.76,4.6,5.74,1.8,'応答テンポの目標','Realtimeの最初の音声受信から、\n骨格が使えるまでの追加待ちを1秒以内へ。')
callout(s,6.78,4.6,5.74,1.8,'運用上の条件','上半身のみ表示／研究室Windowsで再現／\n既存環境への変更を抑える。')

# 04 — model taxonomy
s=slide('7モデルを実生成。出力する役割が異なるモデルを含む',
        '話し手のジェスチャー、聞き手の全身反応、頭部反応を区別する',
        '[R1] common-input-times.csv  [R2] README.md  [R8] model_compatibility.md',
        'text-to-vrmaはARDYを用いる変換・後処理経路であり独立した動作モデルではない。公式Node関数と形式変換は確認したが、今回の7モデル実測に実生成データは含まない。MaAIは生徒音声を使い、ReactMotionは会話デモで生徒の認識文を使う。')
rows=[['Kimodo','話し手・全身','テキスト','公式オンライン／B300'],['ARDY','話し手・全身','テキスト','Core8／CPU特徴＋CUDA'],['MotionLCM','話し手・全身','テキスト','HumanML3D系'],['MoMask','話し手・全身','テキスト','HumanML3D系'],['MMM','話し手・全身','テキスト','HumanML3D系'],['ReactMotion','聞き手・全身','テキスト','会話では生徒の認識文'],['MaAI','聞き手・頭部','音声','頭部パラメーター・うなずき']]
table(s,.76,2.36,[2.15,2.65,1.65,5.35],['モデル','役割・出力','入力','今回の経路'],rows,row_h=.45,font=14)
text(s,.83,6.23,11.6,.45,'text-to-vrma：ARDYの出力をVRMAへ変換する別経路。統合済み・同条件の実生成時間は未測定。',size=15,color=MUTED)

# 05 — hardware
s=slide('研究室PCの制約を意識しつつ、GPU環境を段階的に拡張',
        'RTX 4090の制限実験とB300実験は、RTX 5070 / Windowsの実測ではない',
        '[R5] reproducibility/hardware.json  [R6] benchmark/hardware.json  docs/windows_lab.md',
        'RTX4090はCPUスレッドとaffinityを8に設定、PyTorch allocator上限を12227MiBに設定。GPU自体は24GBであり12GB GPUそのものではない。RAM32GBのハード上限は未設定。B300はCPU推論8スレッド、ホスト可視192論理CPUを割当コア数と混同しない。API観測の割当は24vCPUと251GB。Kimodoの旧共通5文は4090ではなく公式オンラインL40S表示の経路。')
rows=[['GPU','RTX 5070 ×1','RTX 4090 ×1','B300 SXM6 AC ×1'],['VRAM','12GB','24GB／allocator制限','公称288GB'],['CPU','Ryzen 7 5700X','AMD EPYC 7K62','Intel Xeon 6740E'],['CPU設定','8コア16スレッド','推論8スレッド・affinity 8','割当24vCPU／推論8スレッド'],['RAM','32GB','32GBのハード上限なし','251GB（API表示）'],['保存領域','SSD 1TB','クラウド作業領域','コンテナ40＋作業40GB'],['OS','Windows','Linux','Ubuntu 24.04']]
table(s,.76,2.4,[1.65,3.0,3.5,3.65],['項目','研究室PC','7モデル比較のローカルGPU','Kimodo常駐検証'],rows,row_h=.47,font=13)
text(s,.82,6.4,11.7,.36,'Kimodoの旧比較：公式オンラインGPU（L40S表示）。動画の描画：クラウドCPU / SwiftShader。',size=13,color=MUTED)

# 06 — common input
s=slide('共通の英語学習5区間と、生徒→先生の短い会話を使用',
        '日本語・英語を含む利用者指定文を、英訳や動作命令に置換せず入力',
        '[R1] common-input-times.csv  [R2] audio-input-dialogue/*/measurement.json',
        '共通5文の後期比較は原文をそのまま使用。最初期の文分割デモは発話に合わせた英語動作命令を使っており、その結果を後期共通入力と混同しない。ReactMotionとMaAIは聞き手として評価。会話の教師返答は固定しており自由回答の試験ではない。')
sentences=['こんにちは！','今日も一緒に楽しく英語を勉強しましょう！','まずは英語で挨拶してみよう。','Hello! How are you today?',"元気なときは、I'm happy! って言ってみてね。"]
for i,t in enumerate(sentences):
    yy=2.38+i*.61
    box(s,.8,yy,.42,.42,TEAL,radius=True)
    text(s,.8,yy+.04,.42,.32,str(i+1),size=14,color=WHITE,bold=True,align=PP_ALIGN.CENTER)
    text(s,1.42,yy-.02,7.0,.51,t,size=18)
callout(s,8.65,2.38,3.85,3.6,'会話の入力・返答','生徒（音声1.9秒）\n「先生、こんにちは！」\n\n先生（固定返答）\n「こんにちは！今日も元気そうだね！英会話の練習を始めましょう」',body_size=17)
text(s,.82,6.18,11.4,.45,'音声入力の会話では、実際に受信した先生の返答文から、新規の動作を生成した。',size=17,color=TEAL,bold=True)

# 07 — measurement definitions
s=slide('計測を3段階に分け、Realtimeとの差を明確に定義',
        '同じ「生成時間」でも、読み込み・通信・描画を含むかで値が変わる',
        '[R1–R4] 計測CSV・measurement.json / docs/audio_input_comparison.md',
        'T_audioは生徒発話終了から最初の教師音声チャンク受信まで。T_boneは同じ起点から骨格受信または動作完了観測まで。差はT_bone−T_audio。スピーカー再生の物理遅延、口形の音素一致、運動品質の誤差ではない。動画では両方を同一フレームで開始するよう音声を保留。MP4書き出しはCPU処理。')
for x,title,body in [( .76,'① 生成処理','入力テキスト処理＋動作生成＋骨格変換。\nモデル読み込み・通信は原則別記。'),(4.78,'② 会話の応答待ち','生徒の発話終了 → 骨格受信。\n実際のAPI・通信・起動等を含む。'),(8.80,'③ MP4書き出し','VRM描画＋音声結合＋エンコード。\nオフラインの成果物作成時間。')]:
    callout(s,x,2.5,3.77,2.14,title,body,body_size=15)
box(s,.76,5.03,11.81,1.28,NAVY,radius=True)
text(s,1.0,5.22,11.3,.4,'Realtimeとの差 ＝ 骨格が届いた時刻 − 最初の教師音声が届いた時刻',size=23,color=WHITE,bold=True)
text(s,1.0,5.82,11.1,.30,'動画では骨格まで音声を待たせるため、発話・動作の開始は一致する。待ち時間そのものは残る。',size=13,color='C2D5DA')

# 08 — common totals
s=slide('共通5区間の記録：生成処理と動画化を別々に保存',
        'GPU・入力処理・役割が異なるため、この表だけでモデルの性能順位は決められない',
        '[R1] common-input-times.csv / 値は各5区間の合計',
        'Kimodoは公式オンラインでテキスト処理と通信を含む骨格取得時間。ARDYはCPUテキスト特徴を事前計算し、その実処理時間をCUDA生成に加算した。モデルロードは別、会話版では実際に受け取った教師全文からエンコードする。MaAIは同じ発話の音声を使う。描画はCPU SwiftShaderで一部並行実行。UTC入力→MP4経過時間は待ちや再描画が入るため速度比較に使わない。')
rows=[]
for m in MODELS:
    r=common[m]
    path='公式オンライン・通信込み' if m=='kimodo' else ('CPU特徴＋CUDA生成' if m=='ardy' else 'CUDA生成')
    role='話し手' if m not in ['reactmotion','maai'] else ('聞き手・全身' if m=='reactmotion' else '聞き手・頭部')
    rows.append([NAMES[m],role,f"{float(r['generation_processing_seconds_sum']):.3f}秒",f"{float(r['render_seconds']):.1f}秒",path])
table(s,.76,2.38,[1.8,2.0,2.2,2.0,3.8],['モデル','役割','生成処理・5区間','MP4描画・CPU','生成の計測経路'],rows,row_h=.48,font=14)
text(s,.83,6.42,11.6,.32,'同じ発話音声を各モデルで共有。生成後の再生時間調整・姿勢補間と、元の骨格を区別して保持。',size=13,color=MUTED)

# 09 — comparable fast models
s=slide('同じRTX 4090・入力5区間ではMotionLCMが最短',
        '初回を除く4区間の中央値。文と生成長は区間ごとに異なる（48〜72フレーム）',
        '[R1] common/{motionlcm,mmm,momask}/segments/*/motion-generation.json',
        'MotionLCM 0.0388537359秒、MMM 0.0607730370秒、MoMask 0.2023586521秒。これは同一文の反復中央値ではなく異なる4文の中央値。初回区間は40フレームで0.414、0.527、0.705秒。GPUピークはTorch allocated値で全デバイス使用量や必要VRAMの保証ではない。各モデルの意味適合性・品質は未採点。')
for i,m in enumerate(['motionlcm','mmm','momask']):
    bar(s,NAMES[m],warm[m]['median'],.24,3.55,2.70+i*.87,w=6.75)
rows=[]
for m in ['motionlcm','mmm','momask']:
    w=warm[m]
    rows.append([NAMES[m],f"{w['first']:.3f}秒",f"{w['minimum']:.3f}〜{w['maximum']:.3f}秒",f"{float(common[m]['peak_torch_allocated_mib'])/1024:.2f}GiB"])
table(s,.82,5.38,[2.5,2.6,3.6,3.0],['モデル','初回区間の生成','残り4区間の範囲','Torch最大割り当て'],rows,row_h=.32,font=12)

# 10 — audio input baseline
s=slide('従来の会話経路では、起動・中継の待ちが大きかった',
        '生徒の発話終了を0秒とする。各モデル1回、常駐化前の実測',
        '[R2] audio-response-times.csv / Kimodoは公式オンライン、他はRTX 4090',
        '完了観測の時間は純粋な骨格生成ではない。ローカルGPU経路は起動とモデルロード、RPC、最大5秒の完了ポーリング等を含む。ARDYは言語モデルの読込・CPUエンコードも実施。Realtime接続の旧3秒終了待ちもある。Kimodoは公式オンラインである。ReactMotion/MaAIの聞き手反応を先生のジェスチャー品質ランキングに使わない。')
rows=[]
for m in MODELS:
    a=audio[m]
    rows.append([NAMES[m],f"{float(a['first_teacher_audio_seconds_after_student_end']):.3f}",f"{float(a['motion_generation_seconds']):.3f}",f"{float(a['bone_ready_observed_seconds_after_student_end']):.3f}",f"{float(a['bone_minus_first_realtime_audio_seconds']):.3f}"])
table(s,.76,2.38,[2.3,2.25,2.4,2.4,2.45],['モデル','音声初受信（秒）','生成処理（秒）','動作完了観測（秒）','音声との差（秒）'],rows,row_h=.46,font=14)
callout(s,.79,6.16,11.72,.60,'解釈：これは「モデルの純粋な速さ」の順位ではなく、当時の実装経路の応答待ちの記録。','',body_size=13)

# 11 — controlled B300 benchmark
s=slide('Kimodo / B300：20ステップでは生成単体が1秒未満',
        '同じ教師返答・149フレーム（約4.97秒）・batch=1・各設定3回の中央値',
        '[R3] benchmark/summary.json・hardware.json / Kimodo-SOMA-RP-v1',
        '各設定を1回ウォームアップ後、seed0/1/2で計測。毎回テキスト特徴を再計算。入力処理、CUDA生成・復元、CPU転送、上半身JSON化まで含む。モデルロード・ネットワーク・動画化は除く。動作モデルfloat32、テキストエンコーダーbfloat16。TF32は許可設定であり全カーネルがTF32とは断定しない。torch.compileは使用せず、後処理も無効。100→20ステップの品質・FIDは未評価。')
labels=['FP32 / 100 steps','TF32許可 / 100 steps','TF32許可 / 20 steps']
for i,(label,r) in enumerate(zip(labels,benchmark)):
    bar(s,label,r['bone_ready_seconds'],2.0,4.43,2.65+i*.85,w=5.7,color=TEAL if i==2 else BLUE)
text(s,.89,5.24,5.7,.46,'100→20 steps：処理時間は約77%短縮',size=20,color=TEAL,bold=True)
text(s,.89,5.91,5.7,.68,'20 stepsの画質・動作自然さが\n100 stepsと同等かは未評価。',size=17,color=MUTED)
box(s,7.0,5.17,5.25,1.46,PALE,radius=True)
text(s,7.22,5.34,4.8,.4,'常駐化の前提',size=18,color=TEAL,bold=True)
text(s,7.22,5.89,4.8,.52,'キャッシュ済みモデル読込：約40.2秒\nTorch最大割り当て：約15.3GiB',size=16)

# 12 — live timeline
s=slide('B300でも、骨格が届くまでの追加待ちは約3.25秒',
        '別途実施した音声入力の会話：先生の全文を受信してから動作生成を開始',
        '[R4] dialogue-{fp32-100,tf32-20}/measurement.json / 各1回・同一クライアント時計',
        '高速経路は最初の音声0.685386秒、全文1.673376秒、生成送信1.782977秒、骨格受信3.936996秒。追加待ち3.251610秒。内訳は全文待ち0.987990秒、送信まで0.109601秒、生成0.496237秒、中継・通知・保存用NPZ等を含む残差1.657782秒。残差は純粋なネットワーク遅延ではない。生成した長さは通常144frames/4.8秒、高速162frames/5.4秒で、前スライドの149framesとは別実行。GPUと常駐化、接続終了待ち短縮等を同時に変えており、旧15.395秒からの変化をGPUだけの効果とは扱わない。')
x0,xw=.99,11.05
for row,(mode,label) in enumerate([('fp32-100','通常100 steps'),('tf32-20','高速20 steps')]):
    m=live[mode]; y=2.65+row*1.38
    text(s,x0,y,3.5,.4,label,size=18,bold=True)
    yy=y+.94
    box(s,x0,yy,xw,.035,LINE)
    for t in range(6):
        xx=x0+t/5.3*xw
        box(s,xx,yy-.04,.012,.12,LINE)
        if row==1:text(s,xx-.15,yy+.13,.5,.25,str(t)+'秒',size=10,color=MUTED)
    points=[(m['first_teacher_audio_seconds_after_student_end'],'音声',BLUE),
            (m['teacher_transcript_seconds_after_student_end'],'全文',MUTED),
            (m['bone_ready_observed_seconds_after_student_end'],'骨格',TEAL)]
    for t,label2,c in points:
        xx=x0+t/5.3*xw
        dot=s.shapes.add_shape(MSO_SHAPE.OVAL,Inches(xx-.055),Inches(yy-.04),Inches(.11),Inches(.11))
        dot.fill.solid();dot.fill.fore_color.rgb=rgb(c);dot.line.fill.background()
        text(s,xx-.43,yy-.53,1.15,.52,f'{label2} {t:.3f}',size=13,color=c,bold=True)
    text(s,8.15,y-.03,4.05,.40,f"Realtimeとの差  {m['bone_minus_first_realtime_audio_seconds']:.3f}秒",size=20,color=GOLD,bold=True,align=PP_ALIGN.RIGHT)
text(s,.91,5.54,11.5,.38,'高速設定の追加待ち 3.252秒 の内訳（残差による整理）',size=18,bold=True)
parts=[('全文待ち','0.988秒'),('送信まで','0.110秒'),('骨格生成','0.496秒'),('中継・結果受信等','1.658秒')]
for i,(label,val) in enumerate(parts):
    xx=.91+i*2.95
    box(s,xx,6.05,2.77,.55,PALE,radius=True)
    text(s,xx+.1,6.15,2.57,.35,f'{label}  {val}',size=13,color=TEAL if i==2 else INK,bold=True)

# 13 — embedded demonstrations
s=slide('上半身・正面1080pのデモで、実測した待ち時間を確認',
        'PowerPoint：画像をクリックして動画再生 ／ PDF：同梱mediaフォルダーのMP4を再生',
        '[R4] video-{fp32-100,tf32-20}/demo.mp4 / AvatarSample_VRM1.0・pixiv VRoid Project',
        'この動画は実測した待ち時間を再現するオフライン再生でありライブ録画ではない。音声は実際のRealtime応答、動作は受信した全文から実生成。発話と動作を同一フレームにそろえて開始する。動画内の表示時刻と30fpsの切り上げにより、実再生開始は通常5.00秒、高速3.9667秒。PowerPointでは2本のMP4を埋め込む。PDFは静止画プレビューで音声動画は同梱MP4またはindex.htmlを使用。')
for i,mode in enumerate(['fp32-100','tf32-20']):
    x=.76+i*6.08
    movie(s,f'b300-{mode}',x,2.45,5.73,3.223)
    label='通常 / FP32・100 steps' if i==0 else '高速 / TF32許可・20 steps'
    text(s,x,5.89,5.73,.40,label,size=20,bold=True,color=TEAL)
    text(s,x,6.37,5.73,.32,'▶ 同梱MP4を開く',size=14,color=BLUE,link=f'media/b300-{mode}.mp4')

# 14 — segmentation and upper body
s=slide('文ごとに発話・動作を同期し、連結する経路を実装',
        '一括生成の既存コードは保持。文分割版・ARDY版・上半身版は独立した経路',
        '[R7] segmented/english-lesson*/README.md  [R4] B300 README.md',
        '初期の分割デモでは発話に対応する英語動作指示を使用。Kimodo骨格合計72.91秒、音声25.32秒、描画237.03秒、成功処理335.27秒。ARDY Horizon40コミュニティSpaceは骨格115.29秒、描画1038.91秒、成功処理1154.20秒、最初の入力からMP4完成1219.86秒。これらは後期Core8/4090の共通原文比較と異なる。区間音声の開始位置はPCM検査で0サンプル差。短い音声の区間はモデル最短長の骨格を生成して再生速度を調整、元骨格を保持。B300は全77関節を生成後、上半身67関節を抽出。腰・脚の表示を固定するため上半身専用モデルへの高速化ではない。')
for i in range(5):
    x=.85+i*2.46
    box(s,x,2.54,2.16,1.42,PALE,radius=True)
    text(s,x+.14,2.73,1.88,.35,f'区間 {i+1}',size=18,bold=True,color=TEAL)
    text(s,x+.14,3.28,1.88,.48,'発話 ＋ 動作\n同時に開始',size=15)
    if i<4:text(s,x+2.21,3.01,.22,.4,'→',size=19,color=MUTED)
callout(s,.82,4.34,5.7,2.22,'同期・連結','区間の開始を同じフレームへそろえる。\n境目の姿勢は最大250ms補間。\n元の骨格・音声・時間記録を保持。',body_size=18)
callout(s,6.79,4.34,5.7,2.22,'上半身表示の扱い','Kimodoは全身77関節を生成し、\n上半身67関節を抽出。腰・脚を固定。\n上半身のみを生成するモデルではない。',body_size=18)

# 15 — costs
s=slide('B300の1会話は約5円相当。ただし借りている間は連続課金',
        '$8.99 / 時、1ドル200円で換算。モデル常駐済み・起動と待機の費用は別',
        '[R4] usage・入力開始〜骨格受信  [R9] trial-cleanup.json  [P1] OpenAI公式モデル料金',
        'GPU料金は生徒音声入力開始から骨格受信までの約6.8725秒/5.8374秒を時間換算。骨格生成単体だけの費用0.97円/0.25円を総費用とは扱わない。Realtimeはinput text89/audio19、output text38/audio96（通常）、output text61/audio108（高速）。100万tokenあたりtext input$4/output$24/audio input$32/output$64。reasoning23tokensはoutput text61に含まれる内訳として二重加算しない。料金確認2026-10-15、確定請求額は未取得。ASR・ストレージ・起動・待機・動画化は合計から除外。研究用の録音済み入力作成費用も1会話の見積もりに含まない。')
c1,c2=costs['fp32-100'],costs['tf32-20']
rows=[['入力音声開始→骨格受信',f"{c1['request_window_seconds']:.3f}秒",f"{c2['request_window_seconds']:.3f}秒"],
      ['上記時間のGPU料金',f"約{c1['gpu_yen']:.2f}円",f"約{c2['gpu_yen']:.2f}円"],
      ['Realtime API・usageから算出',f"約{c1['realtime_yen']:.2f}円",f"約{c2['realtime_yen']:.2f}円"],
      ['小計／会話（ASR等は別）',f"約{c1['subtotal_yen']:.2f}円",f"約{c2['subtotal_yen']:.2f}円"]]
table(s,.83,2.4,[5.3,3.2,3.2],['料金の対象','通常100 steps','高速20 steps'],rows,row_h=.57,font=17,highlights=(3,))
text(s,.87,5.40,11.55,.43,'実運用：1時間100リクエストなら、GPU代だけで約18円／回 ＋ API料金等。',size=20,color=GOLD,bold=True)
text(s,.87,6.12,11.55,.60,'検証一式のGPU＋ストレージ概算：RTX 4090 約500円 ／ B300 約925円（API料金別）。\n両Podとも終了・削除を確認済み。料金は確定請求額ではない。',size=15,color=MUTED)

# 16 — lab deployment
s=slide('研究室PCでは、小型モデルから常駐実行を検証する',
        'Windows / RTX 5070 12GB / RAM32GB。セットアップ用スクリプトと専用仮想環境を用意',
        'docs/windows_lab.md / configs/lab-windows.json / [R1][R3] VRAM記録',
        'SSH・WSL・Dockerを前提としないWindowsネイティブ手順。Python/Node/FFmpeg/BuildToolsを事前チェックし、専用venvと固定ソースを用いる。現物Windows/5070のビルドと実推論は未検証。Torchピークだけで必要VRAMを保証しない。KimodoのGPUテキストエンコーダー込み15.3GiB構成は12GBに収まらない。CPUテキストエンコーダーは公式に提供されるがCPU待ちが増える可能性があり5070で再測定する。初回loadやRAM容量、Blackwell対応CUDAビルドも確認が必要。')
callout(s,.81,2.43,5.7,1.66,'まず試す：MotionLCM / MMM / MoMask','4090ではTorch最大割り当て約0.9〜1.5GiB。\nWindows実機でGPU演算と生成時間を確認。',body_size=17)
callout(s,6.81,2.43,5.7,1.66,'Kimodo：CPU側へテキスト処理を分離','今回の全GPU常駐は約15.3GiB。\n12GBでは同じ構成を使えない。',body_size=17)
steps=[('1','環境構築','既存スクリプト＋専用venv'),('2','常駐化','重み・言語モデルを事前読込'),('3','同じ入力で計測','音声初受信・骨格受信を記録'),('4','品質を確認','意味適合・自然さ・つなぎ目')]
for i,(num,title,body) in enumerate(steps):
    x=.82+i*3.03
    text(s,x,4.75,.5,.65,num,size=32,color=TEAL,bold=True)
    text(s,x,5.53,2.72,.45,title,size=20,bold=True)
    text(s,x,6.15,2.72,.46,body,size=14,color=MUTED)

# 17 — paper and quality
s=slide('論文の順位との比較は限定的。品質を含む優劣は未確定',
        'ユーザー提示のMoSCo比較表と、今回の実験では入力・生成長・計測範囲が異なる',
        '[U1] ユーザー提示のMoSCo紹介画像（Table 1）  [R1] MotionLCM・MoMask実測',
        'MoSCo表はユーザーが提示した紹介画像から引用。原論文Table1の独立再検証や全14モデルの再現ではない。画像のAITSはMotionLCM0.030秒、MoMask0.120秒、RTX4090/HumanML3D。今回の初回を除く4文の中央値では0.039秒/0.202秒で順序は同じだが条件や統計量が違う。MoSCo本体、TEMOS、MotionMamba等は実行していない。FIDを今回の日本語会話ジェスチャーにそのまま適用して順位を決めない。')
rows=[['MotionLCM','0.030秒','0.039秒'],['MoMask','0.120秒','0.202秒']]
table(s,.85,2.48,[3.15,4.15,4.4],['共通して登場するモデル','提示資料のAITS','今回・初回を除く4区間中央値'],rows,row_h=.66,font=19)
text(s,.90,4.77,11.5,.48,'この2モデルの速度の順序は一致。ただし、論文の数値を再現したとは言えない。',size=21,color=TEAL,bold=True)
text(s,.90,5.58,11.5,.86,'未評価：日本語の意味適合／英語学習の発話に合う動作／動作自然さ／FID／\n20ステップの品質低下／連続会話でのp50・p95。',size=20,color=MUTED)

# 18 — conclusion and next experiment
s=slide('次は常駐・短区間化と、品質評価を組み合わせる',
        'GPUの大型化だけでは、今回の会話経路の追加待ちを1秒以内にできなかった',
        '判断根拠：[R1–R4] / 右の施策は提案であり、達成時間の予測ではない',
        '達成済みと未達を明示。B300で生成単体1秒未満は確認したが、会話での差は3.252秒。次の仮説はモデル常駐の徹底、全文完了前の短い意味区間での開始、Jupyter中継から直接サービスへの変更、保存用NPZ転送を同期経路から外す。これらの効果は未測定。複数音声・複数seed・反復回数を増やして品質とp50/p95を測り、5070Windows実機と同条件に近づける。')
callout(s,.8,2.42,5.71,3.52,'確認できたこと','7モデルの新規生成と動画化。\n文単位の発話・動作同期と連結。\nB300の生成単体：最短中央値0.435秒。\n会話の追加待ち：高速設定で3.252秒。',body_size=20)
callout(s,6.79,2.42,5.71,3.52,'次の検証','① 全モデルを事前読込して比較\n② 全文待ちを短い意味区間へ変更\n③ 骨格を直接返し、保存処理を分離\n④ 5070実機＋反復計測＋品質評価',body_size=20)
text(s,.87,6.27,11.55,.43,'現時点の選定候補：速度重視はMotionLCM / MMM。Kimodoは品質確認と応答経路の改善を継続。',size=17,color=TEAL,bold=True)

# 19 — appendix: experiment progression
s=slide('付録：初期調査からの到達点と、未測定の経路',
        '古い「未実行」の記録を、後続の成功記録と混同しない',
        '[R7] segmented/english-lesson*/README.md  [R8] execution_results.md・model_compatibility.md',
        '初期CPU環境では9モデルを調査しARDY無条件CPUとKimodo公式オンラインの動作指示を実行。後続でARDY Horizon40のテキスト条件付き生成、Core8のGPU実生成、7モデル比較とB300Kimodoを追加した。初期のStage3未達という表記は初期日付の範囲。会話内容の意味に合った自然なジェスチャーの品質検証は引き続き未達。text-to-vrmaは形式変換fixtureをモデル生成成功に数えない。')
rows=[['Kimodo','初期：公式オンラインの動作指示','後期：共通5文・音声会話・B300実生成'],['ARDY','初期：無条件CPU診断','後期：Horizon40遠隔／Core8 CUDA実生成'],['text-to-vrma','ARDYエンジン選択・形式統合','モデルの同条件実生成時間は未測定'],['LoM / MIBURI / StreamTalk','公式コード・依存・重み配信を調査','今回の比較条件では実推論未検証'],['LLM-Gesture / ViBES body','資産・公開経路等を調査','今回の比較条件では実推論未検証'],['FreeTalker / AgentHands','コード調査／役割を確認','実生成の比較には未収録']]
table(s,.77,2.4,[3.45,4.0,4.35],['対象','初期調査・導入','今回の報告上の扱い'],rows,row_h=.55,font=13)
text(s,.85,6.50,11.6,.29,'公開コード・ダウンロード可能な重み・推論成功・会話品質の検証は、それぞれ別の到達点。',size=14,color=MUTED)

# 20 — appendix: segmented data
s=slide('付録：初期の文分割デモは、発話に合わせた動作指示を使用',
        '共通原文5区間の後期比較とは、入力・モデル・サービス・描画条件が異なる',
        '[R7] reports/segmented/english-lesson*/README.md / 成功処理の合計',
        'Kimodoは公式オンライン、ARDYはHorizon40の公開コミュニティSpace。両方とも原発話そのままではなく発話に合わせた英語動作指示を使用。ARDYの音声は既存のKimodo音声を共有し、追加OpenAI音声生成は0回。各動画は14.133秒、424フレーム、1080p/30fps。最短長制約を満たす新規骨格を生成し再生速度を調整した区間がある。これはライブ会話の待ち時間ではない。')
rows=[['モーションモデル','Kimodo SOMA-RP-v1','ARDY Core / Horizon40'],['利用経路','NVIDIA公式オンライン','公開コミュニティSpace'],['骨格生成・5区間','72.91秒','115.29秒'],['音声生成・今回分','25.32秒','0秒（同じ既存音声を共有）'],['連結込みMP4書き出し','237.03秒','1,038.91秒'],['成功処理の合計','335.27秒','1,154.20秒'],['完成動画の長さ','14.133秒','14.133秒']]
table(s,.80,2.4,[4.0,3.8,4.0],['項目','Kimodo版','ARDY版'],rows,row_h=.48,font=15)
text(s,.88,6.49,5.35,.29,'▶ Kimodoの分割デモ',size=14,color=BLUE,link='media/segmented-english-lesson.mp4')
text(s,6.93,6.49,5.35,.29,'▶ ARDYの分割デモ',size=14,color=BLUE,link='media/segmented-english-lesson-ardy.mp4')

# 21 — appendix: sources and reproducibility
s=slide('付録：計測原本・固定バージョン・再現手順',
        'Gitリポジトリ：github.com/nk-an-nk/textToMotion / work　　実験コード基準：3a37d6e',
        '原本はGitのworkブランチ。再集計値・費用式は同梱measurements.json。',
        'R1=reports/model-comparison/runpod-20261014/common-input-times.csvと各生成JSON。R2=同audio-response-times.csvと各measurement.json。R3=reports/kimodo-b300-20261015/benchmark/summary.json/hardware.json。R4=同dialogue-times.csvとdialogue-*/measurement.json/video-*/demo.mp4。R5=旧reproducibility/hardware.json/source-and-weights.json。R6=B300environment.json/benchmark/hardware.json。R7=reports/segmented/english-lesson*/README.md。R8=reports/execution_results.md/model_compatibility.md。R9=両試験trial-cleanup.json。U1=ユーザー提示のMoSCo紹介画像（原論文独立検証なし）。P1=OpenAIのgpt-realtime-2.1公式モデルページ、2026-10-15に料金確認。B300ソース58e781898b3d7e328a676a75d3e338c45dce3ad9、checkpoint revision defbe1f34f5fd031eb0ccfe19f3f92a9880c287b。MNTPとsupervisedの各448tensor照合を通った経路のみ報告値に使用。学習済み重みとVRM本体は資料へ再配布していない。')
refs=[('[R1・R2] 7モデル比較の記録','reports/model-comparison/runpod-20261014/README.md'),
      ('[R3・R4・R6] Kimodo / B300の計測・動画','reports/kimodo-b300-20261015/README.md'),
      ('[R5] GPU条件・ソースと重みのハッシュ','reports/model-comparison/runpod-20261014/reproducibility/source-and-weights.json'),
      ('[R7] 文分割デモの入力・同期・計測','reports/segmented/README.md'),
      ('研究室Windowsのセットアップ手順','docs/windows_lab.md')]
for i,(label,path) in enumerate(refs):
    text(s,.92,2.43+i*.56,11.5,.42,label,size=18,color=BLUE,bold=True,link=REPO+path)
text(s,.92,5.48,11.35,.38,'B300：PyTorch 2.8.0+cu129 / CUDA 12.9 / Python 3.12.3',size=18,bold=True)
text(s,.92,6.04,11.35,.55,'ソース・重みrevision・LoRA各448テンソルを検証。元NPZ・骨格JSON・WAV・時刻・usageを保存。\n実装テスト：Python112件／JavaScript22件。ライブWebRTC＋ローカルGPUの連続対話は未検証。',size=15,color=MUTED)

# 22 — appendix: navigation to embedded demonstrations
s=slide('付録：全18本のデモ動画をPowerPoint内に収録',
        'モデル名・画像をクリックすると、会話と共通5文の動画スライドへ移動',
        '[R2] audio-input-dialogue/*/demo.mp4 / AvatarSample_VRM1.0・pixiv VRoid Project',
        '7モデルの会話と共通5文で14本、B300比較2本、初期の文分割2本の全18本をPPTX内に埋め込む。画像は外部MP4へのリンクではなく埋め込み動画スライドへの移動。会話動画は実音声入力と実モデル生成の計測値を再現するオフライン再生。実マイクのライブ録画ではない。ARDYは187秒の待ちが含まれる。ReactMotionとMaAIは聞き手。MaAIは今回の挨拶では最大p_nod0.3219で0.5閾値を超えず、うなずきイベントを追加していない。')
video_menu=s
menu_shapes={}
for i,model in enumerate(MODELS):
    row,col=divmod(i,4);x=.80+col*3.08;y=2.40+row*2.03
    p=picture(s,OUT/f'assets/dialogue-{model}.png',x,y,2.82,1.44,crop=(.23,.10,.77,.81))
    t=text(s,x,y+1.51,2.85,.38,'▶ '+NAMES[model]+('（聞き手）' if model in ['reactmotion','maai'] else ''),size=15,color=BLUE,bold=True)
    menu_shapes[model]=[p,t]
t=text(s,10.07,4.67,2.24,.43,'▶ B300比較へ',size=15,color=BLUE,bold=True)
t.click_action.target_slide=prs.slides[12]
segmented_menu=text(s,10.07,5.24,2.24,.43,'▶ 文分割デモへ',size=15,color=BLUE,bold=True)
text(s,10.07,5.82,2.24,.40,'動画はすべて埋め込み',size=12,color=MUTED)

# 23–29 — both complete videos for each of the seven models
for model in MODELS:
    listener=model in ['reactmotion','maai']
    role='聞き手の反応' if listener else '話し手の動作'
    s=slide(f'デモ動画：{NAMES[model]} / {role}',
            'スライドショーで動画をクリックして再生。左右の動画は個別に再生できます。',
            f'[R1・R2] {model} / AvatarSample_VRM1.0・pixiv VRoid Project',
            f'{NAMES[model]}の会話動画と共通5文の動画を、切り詰めずに全編埋め込み。会話では実測した待ちを再現するオフライン再生。生成・API・動画の再実行は行っていない。PDFは静止画で、外部MP4への補助リンクを用いる。左右を同時再生すると音声が重なるため、発表時は1本ずつ再生する。',
            section='動画付録 / 全18本をスライド内で再生')
    for sh in menu_shapes[model]:sh.click_action.target_slide=s
    for i,group in enumerate(['dialogue','common']):
        x=.76+i*6.08
        text(s,x,2.19,5.73,.39,'生徒 → 先生の会話' if group=='dialogue' else '共通の英語学習5区間',size=20,bold=True,color=TEAL)
        movie(s,f'{group}-{model}',x,2.80,5.73,3.223)
        caption=(f"発話終了→動作完了観測：{float(audio[model]['bone_ready_observed_seconds_after_student_end']):.3f}秒"
                 if group=='dialogue' else
                 f"5区間の生成処理合計：{float(common[model]['generation_processing_seconds_sum']):.3f}秒")
        text(s,x,6.14,5.73,.34,caption,size=14,color=MUTED)
        text(s,x,6.59,4.2,.28,'▶ MP4を直接開く（補助リンク）',size=11,color=BLUE,link=f'media/{group}-{model}.mp4')
    back=text(s,10.23,6.59,2.20,.30,'← 動画目次へ',size=12,color=BLUE,bold=True,align=PP_ALIGN.RIGHT)
    back.click_action.target_slide=video_menu

# 30 — initial segmented pair
s=slide('デモ動画：文ごとの発話・ジェスチャーを同期して連結',
        '初期の文分割デモ：発話に合わせた英語の動作指示を使用した別条件の実験',
        '[R7] segmented/english-lesson* / AvatarSample_VRM1.0・pixiv VRoid Project',
        'KimodoとARDY Horizon40の初期文分割動画を全編埋め込み。音声を共有し各区間の発話とジェスチャーを同じフレームで開始して連結した。後期の共通原文5区間比較とは入力と生成経路が異なる。2本とも既存の14.133秒、424フレームの完成動画。',
        section='動画付録 / 全18本をスライド内で再生')
segmented_menu.click_action.target_slide=s
for i,(media_id,label) in enumerate([('segmented-english-lesson','Kimodo / 公式オンライン'),
                                     ('segmented-english-lesson-ardy','ARDY / Horizon40')]):
    x=.76+i*6.08
    text(s,x,2.19,5.73,.39,label,size=20,bold=True,color=TEAL)
    movie(s,media_id,x,2.80,5.73,3.223)
    text(s,x,6.14,5.73,.34,'5区間を連結・音声付き・14.133秒',size=14,color=MUTED)
    text(s,x,6.59,4.2,.28,'▶ MP4を直接開く（補助リンク）',size=11,color=BLUE,link=f'media/{media_id}.mp4')
back=text(s,10.23,6.59,2.20,.30,'← 動画目次へ',size=12,color=BLUE,bold=True,align=PP_ALIGN.RIGHT)
back.click_action.target_slide=video_menu

assert len(prs.slides) == 30
media=read(OUT/'media-index.json')
assert len(embedded_videos)==len(media)==18
assert {m['id'] for m in embedded_videos}=={m['id'] for m in media}
pptx_path = OUT/'textToMotion_experiment_report_20261016.pptx'
prs.save(pptx_path)
with zipfile.ZipFile(pptx_path) as package:
    movies=[p for p in package.namelist() if p.startswith('ppt/media/') and p.endswith('.mp4')]
    packaged_hashes={hashlib.sha256(package.read(p)).hexdigest() for p in movies}
    assert len(movies)==18
    assert packaged_hashes=={m['sha256'] for m in embedded_videos}
(OUT/'embedded-video-index.json').write_text(json.dumps(embedded_videos,ensure_ascii=False,indent=2)+'\n')
(OUT/'slide-outline.json').write_text(json.dumps(outline,ensure_ascii=False,indent=2)+'\n')
md=['# 音声対話 × Text-to-Motion × VRM：報告スライド原稿','',
    '報告日：2026-10-16（日本時間）。本編18枚、付録12枚。全18本の動画をPowerPoint内に埋め込み。','']
for row in outline:
    md += [f"## {row['slide']:02d}. {row['title']}", '', row['subtitle'], '', row['notes'], '', '出典：'+row['source'], '']
(OUT/'speaker-notes.md').write_text('\n'.join(md))

media=read(OUT/'media-index.json')
cards=[]
group_labels={'dialogue':'7モデル：生徒→先生の会話','common':'7モデル：共通5区間','b300':'Kimodo / B300','segmented':'初期の文分割デモ'}
for group,label in group_labels.items():
    cards.append('<h2>'+html.escape(label)+'</h2><div class="grid">')
    for m in media:
        if m['group'] != group: continue
        cards.append('<article><h3>'+html.escape(m['name'])+'</h3><video controls preload="none" src="'+html.escape(m['path'])+'"></video><p><a href="'+html.escape(m['path'])+'">MP4を開く</a></p></article>')
    cards.append('</div>')
page='''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Text-to-Motion 実験報告</title><style>
body{font-family:system-ui,'Noto Sans CJK JP',sans-serif;background:#f0f5f5;color:#183440;margin:0;padding:40px;line-height:1.75}main{max-width:1200px;margin:auto}h1{font-size:30px}h2{margin-top:48px;color:#007f80}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:24px}article{background:white;padding:20px;border-radius:12px}video{width:100%;aspect-ratio:16/9;background:#122b3a}a{color:#3269ac}header{background:#122b3a;color:white;padding:28px;border-radius:12px}header a{color:#bfe7e6}.note{font-size:14px;color:#5b707b}
</style><main><header><h1>音声対話 × Text-to-Motion × VRM</h1><p>実験報告 / 2026-10-16 / 本編18枚＋付録12枚 / PowerPointに動画18本を埋め込み</p><p><a href="textToMotion_experiment_report_20261016.pdf">PDF</a>　<a href="textToMotion_experiment_report_20261016.pptx">PowerPoint</a>　<a href="speaker-notes.md">発表者ノート</a></p></header><p>会話動画は、録音済み合成音声をRealtimeへ送って得た実測待ち時間の再現です。ライブ録画ではありません。発話・動作は骨格受信まで音声を待たせて同時に開始します。</p><p class="note">ReactMotionは聞き手の全身、MaAIは頭部反応です。初期の文分割デモと後期の共通原文比較では、入力・モデル・計測経路が異なります。Avatar: AvatarSample_VRM1.0 / pixiv VRoid Project。</p>'''+''.join(cards)+'</main></html>'
(OUT/'index.html').write_text(page)

readme='''# 実験報告スライド（2026-10-16・日本時間）

- `textToMotion_experiment_report_20261016.pptx`：編集可能な30枚。全18本のデモ動画を埋め込み。PPTX単体でも動画を保持します。
- `textToMotion_experiment_report_20261016.pdf`：閲覧・配布用。動画は静止画プレビュー。
- `index.html`：資料・動画一覧。MP4（H.264/AAC）対応ブラウザーではインターネットなしで同梱18本を再生できます。
- `speaker-notes.md`：日本語の発表者ノート・出典。PowerPointのノート欄にも収録。
- `measurements.json`：原本から再集計した数値と費用計算の前提。
- `media/`：B300会話2本、7モデル会話7本、共通5区間7本、初期文分割2本。
- `embedded-video-index.json`：全18本の埋め込み先スライド番号と元動画のSHA256。

動画の場所：B300比較は13枚目、7モデルの会話・共通5文は23〜29枚目、初期の文分割は30枚目。22枚目の動画目次から各スライドへ移動できます。PowerPointのスライドショーで動画をクリックすると再生できます。

ZIPを展開し、フォルダー構造を保ったまま利用してください。PDFでは動画を再生できません。PowerPointの動画再生が利用環境で制限される場合は `index.html` または `media/` のMP4を使用してください。ブラウザーがMP4に非対応の場合は、MP4を対応する動画プレイヤーで開いてください。PPTXの文字・表・棒グラフ・時間軸は編集可能です。フォントはNoto Sans CJK JPを指定しています。PDFではフォントを埋め込んでいます。

実験コードの参照リポジトリ： https://github.com/nk-an-nk/textToMotion/tree/work
参照コミット：`3a37d6e113f16a20fade819b8ba6c113d80d3a3b`

今回の資料作成では、追加の有料GPU起動・音声API呼び出しを行っていません。既存の学習済み重み・VRM本体を再配布していません。デモ映像のアバターはAvatarSample_VRM1.0 / pixiv VRoid Project。

注意：GPU・入力・役割・ロードや通信の含有範囲が異なる結果を、同一条件のモデル順位として扱わないでください。会話実測は各1回、B300単体生成は各3回。生成品質・日本語意味適合・FID・RTX5070 Windows実機・ライブマイク連続対話は未評価または未検証です。料金は計測時間と記録usageからの概算で、確定請求額ではありません。

再生成：リポジトリのルートで `python scripts/build_experiment_report.py` を実行。画像・MP4は既存成果物から同梱した `assets/` と `media/` を参照します。PDFはLibreOfficeでPPTXから出力します。
'''
(OUT/'README.md').write_text(readme)
print(json.dumps({'pptx':str(pptx_path),'slides':len(prs.slides),'embedded_videos':len(embedded_videos),'bundled_videos':len(media),'pptx_bytes':pptx_path.stat().st_size},ensure_ascii=False))
