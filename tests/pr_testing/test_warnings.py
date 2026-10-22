from collections import Counter

from pr_test_warnings import (
    BuildWarning,
    find_new_warnings,
    format_warnings_section,
    parse_build_log,
)

# lines from an intel (oneAPI) build of Omega on Chrysalis, with the path of
# the Omega tree shortened to OMEGA
INTEL_LINES = [
    '[ 12%] Building CXX object src/CMakeFiles/OmegaLib.dir/ocn/'
    'OceanInit.cpp.o',
    'OMEGA/components/omega/src/ocn/OceanInit.cpp:54:1: warning: non-void '
    'function does not return a value in all control paths [-Wreturn-type]',
    '1 warning generated.',
    'OMEGA/externals/scorpio/src/gptl/gptl.c:2981:32: warning: if statement '
    'has empty body [-Wempty-body]',
    'OMEGA/externals/scorpio/src/gptl/gptl.c:2981:32: note: put the '
    'semicolon on a separate line to silence this warning',
    'OMEGA/externals/scorpio/src/flib/spio_init.F90(394): warning #5472: '
    "When passing logicals to C, specify '-fpscomp logicals' to get the "
    'zero/non-zero behavior',
    'make[3]: warning: jobserver unavailable: using -j1.  Add '
    "'+' to parent make rule.",
]

# the formats of the other compilers and of CMake
OTHER_LINES = [
    'OMEGA/components/omega/src/ocn/Tend.cu(88): warning #177-D: variable '
    '"x" was declared but never referenced',
    'OMEGA/components/omega/src/drivers/driver.F90:12:7:',
    '',
    '   12 |   integer :: unused',
    '      |       1',
    "Warning: Unused variable 'unused' declared at (1) [-Wunused-variable]",
    'CMake Warning at OMEGA/components/omega/OmegaBuild.cmake:40 (message):',
    '  OMEGA_ARCH is not set',
    '\x1b[01mOMEGA/components/omega/src/base/IO.cpp:7:3: \x1b[35mwarning:'
    '\x1b[0m unused variable [-Wunused-variable]',
]


def test_parse_intel_log(tmp_path):
    warnings = _parse(tmp_path, INTEL_LINES)

    assert warnings == Counter(
        {
            BuildWarning(
                'components/omega/src/ocn/OceanInit.cpp',
                '-Wreturn-type',
                'non-void function does not return a value in all control '
                'paths',
            ): 1,
            BuildWarning(
                'externals/scorpio/src/gptl/gptl.c',
                '-Wempty-body',
                'if statement has empty body',
            ): 1,
            BuildWarning(
                'externals/scorpio/src/flib/spio_init.F90',
                '#5472',
                "When passing logicals to C, specify '-fpscomp logicals' to "
                'get the zero/non-zero behavior',
            ): 1,
        }
    )


def test_parse_other_formats(tmp_path):
    warnings = _parse(tmp_path, OTHER_LINES)

    assert set(warnings) == {
        BuildWarning(
            'components/omega/src/ocn/Tend.cu',
            '#177-D',
            'variable "x" was declared but never referenced',
        ),
        BuildWarning(
            'components/omega/src/drivers/driver.F90',
            '-Wunused-variable',
            "Unused variable 'unused' declared at (1)",
        ),
        BuildWarning(
            'components/omega/OmegaBuild.cmake',
            'CMake',
            'OMEGA_ARCH is not set',
        ),
        BuildWarning(
            'components/omega/src/base/IO.cpp',
            '-Wunused-variable',
            'unused variable',
        ),
    }


def test_moved_warning_is_not_new():
    moved = BuildWarning('a.cpp', '-Wunused', 'unused variable')
    added = BuildWarning('b.cpp', '-Wshadow', 'declaration shadows')

    new = find_new_warnings(Counter({moved: 1}), Counter({moved: 1, added: 1}))

    assert new == [(added, 0, 1)]


def test_second_instance_in_changed_file_is_new():
    warning = BuildWarning('a.cpp', '-Wunused', 'unused variable')

    new = find_new_warnings(
        Counter({warning: 1}), Counter({warning: 2}), ['a.cpp']
    )

    assert new == [(warning, 1, 2)]


def test_second_instance_elsewhere_is_not_new():
    # a header included by one more file, or a line of the baseline log
    # garbled by a parallel build
    warning = BuildWarning('gptl.h', '-Wmacro-redefined', 'macro redefined')

    new = find_new_warnings(
        Counter({warning: 4}), Counter({warning: 5}), ['a.cpp']
    )

    assert new == []


def test_warnings_section(tmp_path):
    baseline = _make_build(tmp_path / 'baseline', INTEL_LINES)
    pr_lines = INTEL_LINES + [
        'OMEGA/components/omega/src/ocn/Tend.cpp:10:5: warning: unused '
        'variable [-Wunused-variable]',
        'OMEGA/externals/ekat/src/Units.cpp:3:1: warning: unused function '
        '[-Wunused-function]',
    ]
    pr = _make_build(tmp_path / 'pr', pr_lines)

    text, count = format_warnings_section(
        str(baseline), str(pr), ['components/omega/src/ocn/Tend.cpp']
    )

    assert count == 2
    assert '2 new warnings, 1 in files this PR changes' in text
    assert (
        '* components/omega/src/ocn/Tend.cpp: [-Wunused-variable] unused '
        'variable' in text
    )
    assert (
        '  externals/ekat/src/Units.cpp: [-Wunused-function] unused function'
        in text
    )


def test_warnings_section_not_compared(tmp_path):
    pr = _make_build(tmp_path / 'pr', INTEL_LINES)
    incremental = _make_build(tmp_path / 'inc', INTEL_LINES, clean=False)

    text, count = format_warnings_section(None, str(pr), [])
    assert count is None
    assert 'no complete build log of the baseline commit' in text

    text, count = format_warnings_section(str(pr), str(incremental), [])
    assert count is None
    assert 'the PR build' in text

    text, count = format_warnings_section(str(pr), str(pr), [])
    assert count == 0
    assert 'No new warnings (3 in the PR build, 3 in the baseline build)' in (
        text
    )


def _parse(tmp_path, lines):
    log = tmp_path / 'build_omega.log'
    omega = tmp_path / 'omega'
    log.write_text(
        '\n'.join(line.replace('OMEGA/', f'{omega}/') for line in lines) + '\n'
    )
    return parse_build_log(str(log), str(omega), str(tmp_path / 'build'))


def _make_build(build_dir, lines, clean=True):
    omega = build_dir.parent / f'{build_dir.name}-omega'
    build_dir.mkdir(parents=True)
    (build_dir / 'build_omega.log').write_text(
        '\n'.join(line.replace('OMEGA/', f'{omega}/') for line in lines) + '\n'
    )
    (build_dir / 'omega_source.txt').write_text(
        f'source: {omega}\nhash: {"a" * 40}\ndescribe: omega\n'
        f'clean_build: {"true" if clean else "false"}\nlog:\n'
    )
    return build_dir
