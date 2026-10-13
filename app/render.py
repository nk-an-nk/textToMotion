"""Headless skeleton video; ffmpeg preserves optional uploaded audio timing."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
import numpy as np


def render_video(motion, output, audio=None):
    if not shutil.which('ffmpeg'):
        raise RuntimeError('FFmpeg が見つかりません。モーション JSON はダウンロードできます。')
    from app import settings
    cache=settings.DATA/'matplotlib-cache'
    cache.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR',str(cache))
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    positions = np.asarray(motion['positions'])
    if len(positions) / motion['fps'] > 120:
        raise ValueError('動画の上限は120秒です。')
    fps = motion['fps']
    stride = max(1, int(np.ceil(fps / 30)))
    frames = positions[::stride]
    low, high = positions.min(axis=(0,1)), positions.max(axis=(0,1))
    center = (low + high) / 2
    radius = max(float((high-low).max()/2), .6)
    figure = Figure(figsize=(6.4,4.8), dpi=100)
    canvas = FigureCanvasAgg(figure)
    axis = figure.add_subplot(projection='3d')
    axis.set(xlim=(center[0]-radius,center[0]+radius), ylim=(center[2]-radius,center[2]+radius),
             zlim=(center[1]-radius,center[1]+radius), xlabel='X (m)', ylabel='Z (m)', zlabel='Y (m)')
    title = 'Synthetic viewer fixture (not model inference)' if motion.get('metadata',{}).get('trained_model_output') is False else 'Motion Lab | ' + motion['skeleton_type']
    if motion.get('metadata',{}).get('task_type')=='unconditional_diagnostic':
        title='ARDY | unconditional diagnostic (no text/audio condition)'
    axis.set_title(title, fontsize=9)
    axis.set_box_aspect((1,1,1))
    axis.view_init(15,-65)
    lines = [axis.plot([],[],[], color='#287aa2', linewidth=3)[0] for parent in motion['parents'] if parent >= 0]
    edges = [(i,p) for i,p in enumerate(motion['parents']) if p >= 0]
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + '.partial.mp4')
    with tempfile.TemporaryFile() as log:
        command = ['ffmpeg','-y','-loglevel','error','-f','rawvideo','-vcodec','rawvideo','-pix_fmt','rgba',
                   '-s','640x480','-r',str(fps/stride),'-i','pipe:0']
        if audio:
            command += ['-i',str(audio),'-map','0:v:0','-map','1:a:0','-c:a','aac','-shortest']
        command += ['-c:v','libx264','-preset','veryfast','-crf','23','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(partial)]
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
        try:
            for frame in frames:
                for line,(i,p) in zip(lines,edges):
                    endpoints = frame[[i,p]]
                    line.set_data_3d(endpoints[:,0],endpoints[:,2],endpoints[:,1])
                canvas.draw()
                process.stdin.write(canvas.buffer_rgba())
            process.stdin.close()
            code = process.wait(timeout=120)
            if code:
                log.seek(0)
                raise RuntimeError('FFmpeg rendering failed: ' + log.read().decode(errors='replace')[-1000:])
            os.replace(partial, output)
        except BaseException:
            process.kill()
            process.wait()
            partial.unlink(missing_ok=True)
            raise
    return output
