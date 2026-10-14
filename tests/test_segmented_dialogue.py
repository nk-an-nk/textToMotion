"""Sample/frame alignment and preservation checks; fixtures are not inference evidence."""
import array
import json
from pathlib import Path
import wave

import pytest

from app.segmented_dialogue import assemble_audio, comparable_text, generate_segments, load_plan, speech_info, split_units


def wav(path, values, rate=24000):
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(rate)
        output.writeframes(array.array('h', values).tobytes())


def test_explicit_units_keep_english_question_and_embedded_exclamation():
    text="こんにちは！/今日も一緒に楽しく英語を勉強しましょう！/まずは英語で挨拶してみよう。/Hello! How are you today?/ 元気なときは、I'm happy! って言ってみてね。/"
    expected=json.loads((Path(__file__).parents[1]/'configs/segmented_english_lesson.json').read_text())
    assert split_units(text)==[unit['text'] for unit in expected['segments']]
    assert len(split_units(text))==5


def test_pcm_concatenation_preserves_voices_and_pads_only_to_video_frame(tmp_path):
    first=[1200]*1800; second=[-2400]*1100
    wav(tmp_path/'first.wav',first); wav(tmp_path/'second.wav',second)
    manifest={'fps':30,'segments':[{'audio':'first.wav','frame_count':3},{'audio':'second.wav','frame_count':2}]}
    destination=assemble_audio(manifest,tmp_path)
    with wave.open(str(destination)) as source:
        pcm=array.array('h'); pcm.frombytes(source.readframes(source.getnframes()))
        assert list(pcm)==first+[0]*600+second+[0]*500
        assert source.getnframes()==4000
    assert speech_info(destination)['duration']==5/30


def test_long_voice_is_never_truncated(tmp_path):
    wav(tmp_path/'voice.wav',[1200]*801)
    with pytest.raises(ValueError,match='truncate'):
        assemble_audio({'fps':30,'segments':[{'audio':'voice.wav','frame_count':1}]},tmp_path)


def test_unsupported_audio_format_is_rejected(tmp_path):
    wav(tmp_path/'voice.wav',[1200]*800,rate=16000)
    with pytest.raises(ValueError,match='24kHz'):
        speech_info(tmp_path/'voice.wav')


@pytest.mark.parametrize('bad_id',['../escape','01/child','', 'a'*41])
def test_plan_cannot_write_outside_segment_directory(tmp_path,bad_id):
    plan={'schema':'motion-lab/segmented-dialogue-plan-v1','fps':30,'segments':[{'id':bad_id,'text':'Hello','motion_prompt':'Wave'}]}
    file=tmp_path/'plan.json';file.write_text(json.dumps(plan))
    with pytest.raises(ValueError,match='IDs'):
        load_plan(file)


def test_resuming_another_plan_does_not_overwrite_existing_outputs(tmp_path):
    config=Path(__file__).parents[1]/'configs/segmented_english_lesson.json'
    saved=tmp_path/'plan.json';saved.write_text('{"existing": true}')
    voice=tmp_path/'voice.wav';voice.write_bytes(b'preserve-existing-user-file')
    with pytest.raises(ValueError,match='different plan'):
        generate_segments(config,tmp_path,budget_usd=5)
    assert json.loads(saved.read_text())=={'existing':True}
    assert voice.read_bytes()==b'preserve-existing-user-file'


def test_transcript_normalization_does_not_accept_rewording_or_translation():
    assert comparable_text("I'm happy!")==comparable_text('I’m happy.')
    assert comparable_text('こんにちは！')!=comparable_text('こんばんは！')
    assert comparable_text('Hello! How are you today?')!=comparable_text('こんにちは！今日の調子はいかが？')
