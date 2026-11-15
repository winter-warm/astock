"""Do not publish a partial catalogue as the completed long course."""
import argparse
import sys
from pathlib import Path
from astock.course_library import catalogue, validate


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', action='store_true')
    parser.add_argument('--prebuild', action='store_true')
    args = parser.parse_args()
    errors = validate(require_complete=args.release or args.prebuild)
    if args.release or args.prebuild:
        from astock.tutorial_release import validate_baseline
        errors.extend(validate_baseline(Path(__file__).resolve().parents[1], packaged=args.release))
    courses = [e for e in catalogue() if e['kind'] == 'course']
    print(f"正式课程 {sum(e.get('status') == 'published' for e in courses)} / {len(courses)}")
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
