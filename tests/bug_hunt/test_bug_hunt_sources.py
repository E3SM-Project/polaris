import json

from bug_hunt_sources import cime_failures, polaris_failures


def test_polaris_failures(tmp_path):
    work = tmp_path / 'omega_hunt'
    (work / 'case_outputs').mkdir(parents=True)
    log = work / 'case_outputs' / 'overflow.log'
    log.write_text(
        'Running step forward\n'
        'StateValidation: PseudoThickness contains 12566 NaN value(s)\n'
        'Traceback (most recent call last):\n'
    )
    results = {
        'schema_version': 1,
        'suite': 'omega_hunt',
        'start_time': '2026-10-28T10:00:00-05:00',
        'provenance': {'machine': 'chrysalis', 'compiler': 'intel'},
        'tasks': [
            {'path': 'ocean/planar/merry_go_round/default', 'status': 'pass'},
            {
                'path': 'ocean/planar/overflow/nonlinear/pstar/order_3',
                'status': 'fail',
                'execution': 'fail',
                'baseline': None,
                'log': 'case_outputs/overflow.log',
            },
        ],
    }
    (work / 'omega_hunt_results.json').write_text(json.dumps(results))

    (failure,) = polaris_failures([str(tmp_path)])
    assert failure.test == 'ocean/planar/overflow/nonlinear/pstar/order_3'
    assert failure.phase == 'run'
    assert failure.row == 'chrysalis/intel'
    assert failure.night == '2026-10-28'
    assert failure.message is not None
    assert failure.message.startswith('StateValidation: PseudoThickness')
    assert failure.excerpt is not None
    assert failure.excerpt.splitlines()[0].startswith('StateValidation')


def test_cime_failures(tmp_path):
    test = 'ERS_Vmct.T62_oQU240.COMEGA-IAF.pm-gpu_gnugpu.G.20261027'
    case = tmp_path / test
    case.mkdir()
    (case / 'TestStatus').write_text(
        f'PASS {test} CREATE_NEWCASE\n'
        f'PASS {test} RUN time=300\n'
        f'FAIL {test} COMPARE_base_rest\n'
    )

    (failure,) = cime_failures([str(tmp_path)])
    assert failure.test == 'ERS_Vmct.T62_oQU240.COMEGA-IAF.G.20261027'
    assert failure.phase == 'compare'
    assert failure.row == 'pm-gpu/gnugpu'
    assert failure.message == 'COMPARE_base_rest failed'
