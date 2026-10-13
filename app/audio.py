import wave
from pathlib import Path


def inspect_wav(path):
    try:
        with wave.open(str(path), 'rb') as audio:
            channels, rate, width, frames = audio.getnchannels(), audio.getframerate(), audio.getsampwidth(), audio.getnframes()
            if channels not in (1, 2) or width not in (1, 2, 3, 4) or not 8000 <= rate <= 192000:
                raise ValueError('WAV は 1/2ch PCM、8–192kHz、8/16/24/32bit を使用してください。')
            duration = frames / rate
            if not .1 <= duration <= 120:
                raise ValueError('音声は 0.1–120秒にしてください。')
            samples = audio.readframes(frames)
            if len(samples) != frames * channels * width:
                raise ValueError('WAV のサンプルが途中で切れています。')
    except (wave.Error, EOFError, OSError) as error:
        raise ValueError('有効な PCM WAV ファイルをアップロードしてください。') from error
    return {'duration': duration, 'sample_rate': rate, 'channels': channels, 'sample_width': width,
            'audio_file': Path(path).name}
