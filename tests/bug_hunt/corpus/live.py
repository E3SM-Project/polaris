#!/usr/bin/env python3
"""
Run the bug hunter's corpus against live GitHub searches and CDash, by
hand, never in CI

Without ``--save``, each match case is matched against live searches and
compared with what it expects, which shows when GitHub's search has
changed under the matcher.  With ``--save``, the live responses replace
the saved ones, for the cases named (or all), so check the comparison
first.  Run this from a shell with a Polaris load script sourced, from the
root of a Polaris checkout.

    python tests/bug_hunt/corpus/live.py
    python tests/bug_hunt/corpus/live.py --save sphere_operator_fix_and_cause
"""

import argparse
import datetime
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
UTILS = os.path.join(HERE, '..', '..', '..', 'utils')
sys.path[:0] = [
    HERE,
    os.path.join(UTILS, 'pr_testing'),
    os.path.join(UTILS, 'bug_hunt'),
]

import corpus  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('cases', nargs='*', help='Cases (default: all)')
    parser.add_argument(
        '--save',
        action='store_true',
        help='Save the live responses in place of the saved ones',
    )
    args = parser.parse_args()
    day = datetime.date.today().isoformat()
    failed = False
    for case in corpus.match_cases():
        if args.cases and case not in args.cases:
            continue
        if args.save:
            count = corpus.save_searches(case, day)
            print(f'{case}: saved {count} searches')
            continue
        outcome = corpus.evaluate_match(case)
        failed = failed or not outcome.ok
        _report(outcome)
    for case in corpus.harvest_cases():
        if args.cases and case not in args.cases:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['git', 'init', '-q', tmp], check=True)
            subprocess.run(
                ['git', '-C', tmp, 'commit', '-q', '--allow-empty', '-m', 'x'],
                check=True,
            )
            if args.save:
                with corpus.every_night_settled():
                    corpus.run_harvest(case, tmp)
                corpus.trim_cdash_index(case)
                print(f'{case}: saved its CDash responses')
                continue
            fetched = os.path.join(tmp, 'cdash_cache')
            ledger = corpus.run_harvest(case, tmp, cache_dir=fetched)
            problems = corpus.check_harvest(case, ledger)
            failed = failed or bool(problems)
            print(f'{case}: {"; ".join(problems) or "as expected"}')
    sys.exit(1 if failed else 0)


def _report(outcome):
    status = 'as expected' if outcome.ok else 'NOT as expected'
    print(
        f'{outcome.case}: {status}; {len(outcome.needs_ruling)} need a '
        f'ruling (noise {outcome.noise}, limit {outcome.max_noise}), '
        f'{len(outcome.broad)} found only by broad terms'
    )
    for label, refs in (
        ('missed', outcome.missed),
        ('ruled but should not be', outcome.wrongly_ruled),
        ('wrong timing', outcome.wrong_timing),
    ):
        if refs:
            print(f'  {label}: {", ".join(refs)}')


if __name__ == '__main__':
    main()
