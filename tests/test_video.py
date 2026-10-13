import json
import shutil
import subprocess
import wave
import numpy as np
import pytest
from app.motion import viewer_fixture
from app.render import render_video


@pytest.mark.skipif(not shutil.which('ffmpeg') or not shutil.which('ffprobe'),reason='FFmpeg / ffprobe unavailable')
def test_render_contains_actual_frames_and_synchronized_audio(tmp_path):
    motion=viewer_fixture();motion['positions']=motion['positions'][:15]
    audio=tmp_path/'tone.wav'
    with wave.open(str(audio),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
        samples=(np.sin(np.arange(8000)/16000*2*np.pi*440)*4000).astype('<i2')
        wav.writeframes(samples.tobytes())
    target=render_video(motion,tmp_path/'video.mp4',audio)
    result=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(target)],capture_output=True,text=True,check=True)
    info=json.loads(result.stdout)
    video=next(s for s in info['streams'] if s['codec_type']=='video')
    assert video['codec_name']=='h264' and int(video['nb_frames'])==15
    assert any(s['codec_type']=='audio' for s in info['streams'])
    assert .45 <= float(info['format']['duration']) <= .7
    assert not (tmp_path/'video.partial.mp4').exists()
