#!/usr/bin/env python3
"""Independent segmented generation entry point; legacy speech and exporters are unchanged."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.segmented_dialogue import generate_segments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('configs/segmented_english_lesson.json'))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--model', choices=('kimodo', 'ardy', 'text_to_vrma'), default='kimodo')
    parser.add_argument('--budget-usd', type=float, default=0)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    result = generate_segments(args.config, args.output_dir, model=args.model, budget_usd=args.budget_usd,
                               data_dir=args.data_dir, seed=args.seed)
    print(json.dumps({'manifest': str(args.output_dir/'manifest.json'), 'segments': len(result['segments']),
                      'duration_seconds': result['duration_seconds'], 'new_motion_inference': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
