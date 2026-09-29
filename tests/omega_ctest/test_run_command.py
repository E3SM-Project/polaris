import subprocess
from pathlib import Path

from jinja2 import Template

TEMPLATE = (
    Path(__file__).resolve().parents[2]
    / 'utils'
    / 'omega'
    / 'ctest'
    / 'run_command.template'
)

PASSED = """\
      Start  1: DATA_TYPES_TEST
 1/2 Test  #1: DATA_TYPES_TEST ..................   Passed    0.44 sec
      Start  2: EOS_TEST
 2/2 Test  #2: EOS_TEST .........................   Passed    1.20 sec

100% tests passed, 0 tests failed out of 2
"""

FAILED = """\
      Start  1: DATA_TYPES_TEST
 1/2 Test  #1: DATA_TYPES_TEST ..................   Passed    0.44 sec
      Start  2: EOS_TEST
 2/2 Test  #2: EOS_TEST .........................***Failed    1.20 sec

50% tests passed, 1 tests failed out of 2

The following tests FAILED:
\t  2 - EOS_TEST (Failed)
"""


def test_summary_file_with_source_record(tmp_path):
    (tmp_path / 'omega_source.txt').write_text(
        f'source: /path/to/omega\n'
        f'hash: {"a" * 40}\n'
        f'describe: Omega-v0.1.0-5510-gaaaaaaaaa\n'
        f'clean_build: true\n'
        f'log:\n'
        f'  aaaaaaaaa Merge pull request #1 from someone/branch\n',
        encoding='utf-8',
    )

    lines = _run(tmp_path, PASSED)

    assert lines == [
        '### CTest unit tests:',
        '- Machine: `chrysalis`',
        '- Compiler: `intel`',
        '- Build type: `Release`',
        f'- Build: `{tmp_path}`',
        f'- Omega: `{"a" * 40}` (`Omega-v0.1.0-5510-gaaaaaaaaa`)',
        '- Result: All tests passed',
        f'- Log: `{tmp_path / "ctests.log"}`',
    ]


def test_summary_file_without_source_record(tmp_path):
    lines = _run(tmp_path, FAILED)

    assert '- Omega: unknown (the build has no omega_source.txt)' in lines
    assert '- Failures (1 of 2):' in lines
    assert '  - `EOS_TEST`' in lines


def _run(build_dir, ctest_output):
    """Run the rendered template with a stand-in for omega_ctest.sh"""
    ctest_script = build_dir / 'omega_ctest.sh'
    ctest_script.write_text(
        f"#!/bin/bash\ncat <<'EOF'\n{ctest_output}EOF\n", encoding='utf-8'
    )
    ctest_script.chmod(0o755)

    template = Template(TEMPLATE.read_text(encoding='utf-8'))
    script = build_dir / 'run_command.sh'
    script.write_text(
        template.render(
            build_dir=build_dir,
            machine='chrysalis',
            compiler='intel',
            build_type='Release',
        ),
        encoding='utf-8',
    )
    subprocess.run(['bash', str(script)], check=True, capture_output=True)

    summary = build_dir / 'ctest_output_for_pr.md'
    return summary.read_text(encoding='utf-8').splitlines()
