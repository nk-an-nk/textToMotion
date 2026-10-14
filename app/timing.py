"""Small timing summaries shared by the UI export and local research batch."""
import csv
import io

FIELDS=['model','example_group','input_text','model_text','status','mp4_status','skeleton_seconds','mp4_render_seconds',
        'total_seconds','device','text_encoder_device','duration_seconds','seed','experiment_id','video','error']


def timing_values(record):
    values=dict(record.get('timings') or {})
    if 'skeleton_seconds' not in values and record.get('task_type')!='import':
        values['skeleton_seconds']=record.get('time_to_first_result')
    return {key:values.get(key) for key in ('skeleton_seconds','mp4_render_seconds','total_seconds')}


def summary_row(record,video=''):
    return {'model':record.get('model_id',''),'example_group':record.get('metadata',{}).get('example_group',''),
            'input_text':record.get('input_text',''),
            'model_text':record.get('model_text',''),'status':record.get('status',''),
            'mp4_status':record.get('render_status','succeeded' if video else 'not_rendered'),
            **timing_values(record),'device':record.get('device',''),
            'text_encoder_device':record.get('model_metadata',{}).get('text_encoder_device',''),
            'duration_seconds':record.get('duration',record.get('duration_requested')),
            'seed':record.get('seed'),'experiment_id':record.get('id',''),'video':video,
            'error':record.get('error') or record.get('render_error') or ''}


def csv_bytes(rows, fields=None):
    output=io.StringIO(newline='')
    writer=csv.DictWriter(output,fieldnames=fields or FIELDS)
    writer.writeheader()
    for row in rows:
        # Excel should display user-supplied text rather than execute it as a formula.
        safe={key:("'"+value if isinstance(value,str) and value.startswith(('=','+','-','@','\t','\r','\n')) else value)
              for key,value in row.items()}
        writer.writerow(safe)
    return output.getvalue().encode('utf-8-sig')
