#!/usr/bin/env python3
"""Decode the actual videos and measure their speech offsets, without provider calls."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import wave

import numpy as np
from scipy.signal import correlate

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.segmented_dialogue import comparable_text, digest, write_json


def pcm(path):
    with wave.open(str(path)) as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 24000):
            raise ValueError('Source must be mono PCM16/24kHz.')
        return np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(np.float64)


def decode(path):
    result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0', '-f', 's16le',
                             '-ac', '1', '-ar', '24000', 'pipe:1'], capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype='<i2').astype(np.float64)


def video(path, frames):
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-f', 'null', '-'], check=True, capture_output=True)
    probe = subprocess.run(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-show_format', '-of', 'json', str(path)],
                           capture_output=True, check=True)
    media = json.loads(probe.stdout)
    v = next(item for item in media['streams'] if item['codec_type'] == 'video')
    a = next(item for item in media['streams'] if item['codec_type'] == 'audio')
    if (v['width'], v['height'], v['r_frame_rate'], int(v['nb_read_frames']), v['codec_name'], a['codec_name']) != (1920, 1080, '30/1', frames, 'h264', 'aac'):
        raise ValueError('Video resolution, codec or frame count differs from the timeline.')
    if abs(float(v.get('start_time', 0))-float(a.get('start_time', 0))) > 1/30:
        raise ValueError('Video and audio stream timestamps are not aligned.')
    return {'frames': frames, 'duration_seconds': float(media['format']['duration']), 'sha256': digest(path), 'full_decode_ok': True}


def alignment(decoded, source, expected):
    # Search one video frame either side of the prescribed position. Report samples,
    # so even a subframe encoder offset can be assessed rather than hidden.
    margin = 800
    start = max(0, expected-margin); end = min(len(decoded), expected+len(source)+margin)
    window = decoded[start:end]
    if len(window) < len(source):
        raise ValueError('The exported audio truncated an utterance.')
    peaks = correlate(window, source, mode='valid', method='fft')
    offset = int(np.argmax(peaks)); observed = start+offset
    match = window[offset:offset+len(source)]
    similarity = float(np.dot(match, source)/max(1, np.linalg.norm(match)*np.linalg.norm(source)))
    if abs(observed-expected) > margin or similarity < .95:
        raise ValueError('Speech PCM does not match the prescribed video interval.')
    return {'expected_start_sample': expected, 'observed_start_sample': observed,
            'offset_samples': observed-expected, 'offset_seconds': (observed-expected)/24000, 'normalized_correlation': similarity}


def validate(manifest_path, movie, destination):
    root = manifest_path.resolve().parent; manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    receipt = json.loads(movie.with_suffix('.json').read_text(encoding='utf-8'))
    if receipt['manifest_sha256'] != digest(manifest_path) or receipt['video_sha256'] != digest(movie):
        raise ValueError('Video provenance hashes do not match.')
    final_pcm = decode(movie); timeline = pcm(root/manifest['timeline_audio']); entries = []
    combined = video(movie, manifest['frame_count'])
    cursor = 0; motion_hashes = set()
    for unit in manifest['segments']:
        speech = json.loads((root/unit['speech_metadata']).read_text(encoding='utf-8'))
        generation = json.loads((root/unit['motion_receipt']).read_text(encoding='utf-8'))
        motion = json.loads((root/unit['motion']).read_text(encoding='utf-8'))
        native = generation.get('metadata', {})
        if unit['start_frame'] != cursor or unit['speech_start_frame'] != cursor or unit['gesture_start_frame'] != cursor:
            raise ValueError('Unit starts are not contiguous and simultaneous.')
        if (digest(root/unit['audio']) != unit['audio_sha256'] or digest(root/unit['motion']) != unit['motion_sha256']
                or comparable_text(speech['transcript']) != comparable_text(unit['text'])
                or motion['metadata']['trained_model_output'] is not True or generation['motion_prompt'] != unit['motion_prompt']):
            raise ValueError('Actual speech/model inference evidence differs from its unit.')
        if native.get('backend') == 'nvidia_official_online_demo':
            downloaded = json.loads((root/unit['motion']).with_name('original.metadata.json').read_text(encoding='utf-8'))
            if downloaded['prompt'] != unit['motion_prompt'] or not downloaded.get('server_success_notification'):
                raise ValueError('Official provider generation did not acknowledge this prompt.')
        motion_hashes.add(unit['motion_sha256'])
        source = pcm(root/unit['audio']); start_sample = cursor*800; end_sample = unit['end_frame']*800
        if not np.array_equal(timeline[start_sample:start_sample+len(source)], source) or np.any(timeline[start_sample+len(source):end_sample]):
            raise ValueError('PCM concatenation changed speech or added unexpected boundary audio.')
        individual_path = root/'segments'/unit['id']/'video.mp4'
        individual = video(individual_path, unit['frame_count'])
        entries.append({'id': unit['id'], 'text': unit['text'], 'transcript_exact': speech['transcript'] == unit['text'],
                        'new_motion_prompt_verified': True, 'individual_video': individual,
                        'combined_speech_alignment': alignment(final_pcm, source, start_sample),
                        'individual_speech_alignment': alignment(decode(individual_path), source, 0)})
        cursor = unit['end_frame']
    if cursor != manifest['frame_count'] or len(timeline) != cursor*800 or len(motion_hashes) != len(entries):
        raise ValueError('Timeline size or independently generated gestures are invalid.')
    if receipt['capture']['camera']['front_alignment'] < .99999 or any(boundary['root_jump_metres'] > 1e-6 for boundary in receipt['capture']['boundaries']):
        raise ValueError('Front view or pose continuity failed.')
    report = {'schema': 'motion-lab/segmented-video-validation-v1', 'combined_video': combined,
              'segments': entries, 'unique_new_model_outputs': len(motion_hashes), 'pcm_timeline_sample_exact': True,
              'front_alignment': receipt['capture']['camera']['front_alignment'],
              'root_boundary_jumps_metres': [boundary['root_jump_metres'] for boundary in receipt['capture']['boundaries']],
              'speech_and_gesture_same_start_frame': True, 'rendered_frames': receipt['rendered_frames'], 'skipped_render_frames': receipt['skipped_render_frames']}
    write_json(destination, report)
    print(json.dumps({'validated_videos': len(entries)+1, 'unique_new_gestures': len(motion_hashes), 'frames': cursor,
                      'max_speech_offset_samples': max(abs(entry['combined_speech_alignment']['offset_samples']) for entry in entries)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Preserve the existing validation result; choose a new output filename.')
    validate(args.manifest, args.video, args.output)
