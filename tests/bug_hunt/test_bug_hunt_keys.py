import pytest
from bug_hunt_keys import (
    cime_phase_and_message,
    cime_phase_to_key,
    first_error_line,
    is_cime_name,
    is_cime_test,
    location_key,
    normalize_message,
    normalize_test,
)


@pytest.mark.parametrize(
    'name, expected',
    [
        (
            'PEM_Vmct.T62_oQU240.GOMEGA-IAF.pm-cpu_gnu',
            'PEM_Vmct.T62_oQU240.GOMEGA-IAF',
        ),
        (
            'PEM_Vmct_Ln9.TL319_EC30to60E2r2.GOMEGA-JRA1p5.pm-gpu_gnugpu'
            '.omega-jra_1958',
            'PEM_Vmct_Ln9.TL319_EC30to60E2r2.GOMEGA-JRA1p5.omega-jra_1958',
        ),
        (
            'ERS_Vmct.T62_oQU240.COMEGA-IAF.chrysalis_intel',
            'ERS_Vmct.T62_oQU240.COMEGA-IAF',
        ),
        ('KPP_CONFIG_GRADIENT_TEST', 'KPP_CONFIG_GRADIENT_TEST'),
        (
            'ocean/planar/overflow/nonlinear/pstar/rpe',
            'ocean/planar/overflow/nonlinear/pstar/rpe',
        ),
    ],
)
def test_normalize_test_drops_machine_and_compiler(name, expected):
    assert normalize_test(name) == expected


def test_the_same_failure_on_four_rows_has_one_test_name():
    rows = ['chrysalis_gnu', 'chrysalis_intel', 'pm-cpu_gnu', 'pm-gpu_gnugpu']
    names = {
        normalize_test(f'PEM_Vmct.T62_oQU240.COMEGA-IAF.{row}') for row in rows
    }
    assert names == {'PEM_Vmct.T62_oQU240.COMEGA-IAF'}


def test_is_cime_test_needs_a_machine():
    assert is_cime_test('SMS_Vmct.ne4_oQU240.WCYCL1850NS-OMEGA.chrysalis_gnu')
    assert not is_cime_test('SMS_Vmct.ne4_oQU240.WCYCL1850NS-OMEGA')
    assert is_cime_name('SMS_Vmct.ne4_oQU240.WCYCL1850NS-OMEGA')
    assert not is_cime_name('ocean/planar/overflow/linear/zstar/rpe')


def test_normalize_message_ignores_numbers_paths_and_addresses():
    one = normalize_message(
        'Error on rank 1475 at 0x7ffd1a2b in /scratch/a/run/Foo.cpp:643'
    )
    two = normalize_message(
        'Error on rank 12 at 0x0000beef in /home/b/build/Foo.cpp:650'
    )
    assert one == two
    assert one == 'error on rank <n> at <addr> in <path>:<n>'


def test_normalize_message_of_nothing():
    assert normalize_message(None) is None
    assert normalize_message('   ') is None


def test_cime_compare_failure():
    output = (
        "2026-10-26 23:52:04: CREATE_NEWCASE PASSED for test 'PEM...'.\n"
        '    PEM.cpl.hi.nc.base did NOT match PEM.cpl.hi.nc.modpes\n'
        'FAIL\n'
        "2026-10-27 00:45:24: compared suffixes suffix1 'base' suffix2 "
        "'modpes'\n"
    )
    phase, message = cime_phase_and_message(output)
    assert phase == 'compare'
    assert message == 'base and modpes history files did not match'


def test_cime_phase_failure():
    output = "2026-10-26 23:57:31: MODEL_BUILD FAILED for test 'ERS...'.\n"
    assert cime_phase_and_message(output) == ('build', 'MODEL_BUILD failed')


def test_cime_run_failure():
    output = (
        "2026-10-07 01:02:03: ERROR: RUN FAIL: Command 'srun --label -n 128 "
        "e3sm.exe' failed\n"
    )
    assert cime_phase_and_message(output) == ('run', 'RUN failed')


def test_first_error_line_skips_launcher_noise():
    output = (
        '1: MPICH ERROR [Rank 1] [job id 55.13] - Abort(3): application '
        'called MPI_Abort(MPI_COMM_WORLD, 3) - process 1\n'
        'srun: error: frontier08447: task 2: Segmentation fault\n'
        '0: ERROR: Mesh file has the wrong sphere radius\n'
    )
    assert first_error_line(output) == (
        '0: ERROR: Mesh file has the wrong sphere radius'
    )
    noise_only = first_error_line(output.splitlines()[1])
    assert noise_only is not None
    assert noise_only.startswith('srun: error')


def test_first_error_line_skips_passing_property_checks():
    output = (
        'mass conservation in output.nc: error=0.000e+00 tol=1.0e-14 [PASS]\n'
        'Error: the forward step failed\n'
    )
    assert first_error_line(output) == 'Error: the forward step failed'


def test_timestamps_are_normalized():
    one = normalize_message('job 55 [Fri Sep 25 15:32:59 2026] failed')
    two = normalize_message('job 56 [Tue Oct 27 01:02:03 2026] failed')
    assert one == two


def test_cime_output_missing():
    assert cime_phase_and_message(None) == ('run', None)


@pytest.mark.parametrize(
    'cime_phase, phase',
    [
        ('COMPARE_base_rest', 'compare'),
        ('COMPARE_base_modpes', 'compare'),
        ('MODEL_BUILD', 'build'),
        ('RUN', 'run'),
        ('BASELINE', 'baseline'),
        ('SOMETHING_NEW', 'run'),
    ],
)
def test_cime_phase_to_key(cime_phase, phase):
    assert cime_phase_to_key(cime_phase) == phase


@pytest.mark.parametrize(
    'where, expected',
    [
        (
            'components/omega/src/ocn/VertMix.cpp:123',
            ('components/omega/src/ocn/VertMix.cpp', 'code'),
        ),
        ('polaris/run/serial.py', ('polaris/run/serial.py', 'code')),
        (
            'ocean/planar/overflow/nonlinear/pstar/rpe',
            ('ocean/planar/overflow/nonlinear/pstar/rpe', 'run'),
        ),
        ('ERS.ne4pg2_oQU480.F2010', ('ERS.ne4pg2_oQU480.F2010', 'run')),
        (
            'PEM.T62_oQU240.COMEGA-IAF.pm-cpu_gnu',
            ('PEM.T62_oQU240.COMEGA-IAF', 'run'),
        ),
    ],
)
def test_location_key(where, expected):
    assert location_key(where) == expected
