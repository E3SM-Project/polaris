"""
The COM results of ISOMIP+ (Yung et al. 2026,
https://doi.org/10.5194/tc-20-2053-2026)

Each model's submission is a registration on the Open Science Framework,
cited in the paper's Table 3, with one file per experiment in the protocol's
format (Asay-Davis et al. 2016, Sect. 3.3).  All are licensed CC-BY 4.0.
For COCO's and NEMO-CNRS's Ocean0, the file is the run tuned to the
protocol's target, a mean melt rate of 30 m yr-1 where the draft is deeper
than 300 m: of COCO's three, the one with a heat-transfer coefficient of
0.0025 (31 m yr-1), and NEMO-CNRS's own Ocean0 file (30 m yr-1) rather
than its two sensitivity runs.
"""

import os
from typing import NamedTuple

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step

#: The paper
CITATION = (
    'Yung, C. K., et al. (2026): Results of the second Ice Shelf-Ocean '
    'Model Intercomparison Project (ISOMIP+), The Cryosphere, 20, '
    '2053-2088, https://doi.org/10.5194/tc-20-2053-2026'
)

#: The x (m) of the ice front in Ocean0-2, beyond which there is no cavity
ICE_FRONT_X = 640.0e3

#: The seconds in a year of 365 days
SECONDS_PER_YEAR = 365.0 * 86400.0

#: The edges (m) of the bins of draft for melt by draft, shared by every
#: model
DRAFT_EDGES = np.arange(-720.0, 1.0, 20.0)


class Submission(NamedTuple):
    """
    A model's COM submission

    Attributes
    ----------
    registration : str
        The identifier of the registration on the Open Science Framework,
        https://doi.org/10.17605/OSF.IO/<registration>

    files : dict of str to tuple of str
        For each experiment, the file's name and its identifier for
        download, https://osf.io/download/<identifier>/
    """

    registration: str
    files: dict


#: Every model's COM submission for Ocean0-2
SUBMISSIONS = {
    'MPAS-Ocean': Submission(
        registration='EAVWY',
        files={
            'ocean0': ('Ocean0_COM_MPAS-Ocean.nc', 'ypcax'),
            'ocean1': ('Ocean1_COM_MPAS-Ocean.nc', '9k65c'),
            'ocean2': ('Ocean2_COM_MPAS-Ocean.nc', 'nwxep'),
        },
    ),
    'POP2x': Submission(
        registration='WVUCT',
        files={
            'ocean0': ('Ocean0_COM_POP2x.nc', 'hpybd'),
            'ocean1': ('Ocean1_COM_POP2x.nc', '3yg9s'),
            'ocean2': ('Ocean2_COM_POP2x.nc', 'hvd25'),
        },
    ),
    'ROMS-UTAS': Submission(
        registration='4HXY9',
        files={
            'ocean0': ('Ocean0_COM_ROMSUTAS.nc', 'zmuqr'),
            'ocean1': ('Ocean1_COM_ROMSUTAS.nc', 'wvtqu'),
            'ocean2': ('Ocean2_COM_ROMSUTAS.nc', '32prb'),
        },
    ),
    'MITgcm-BAS': Submission(
        registration='3HY5G',
        files={
            'ocean0': ('Ocean0_COM_MITgcm_BAS.nc', 'ju4zv'),
            'ocean1': ('Ocean1_COM_MITgcm_BAS.nc', 'tm9ry'),
            'ocean2': (
                'Ocean2_COM_MITgcm_BAS.nc',
                '680b9b0a49a1ec5209568bdc',
            ),
        },
    ),
    'MITgcm-BAS-Coupled': Submission(
        registration='MN2VX',
        files={
            'ocean0': ('Ocean0_COM_MITgcm_BAS_CoupledV3.nc', 'e6hqw'),
            'ocean1': ('Ocean1_COM_MITgcm_BAS_CoupledV3.nc', '5vmkq'),
            'ocean2': ('Ocean2_COM_MITgcm_BAS_CoupledV3.nc', 'sp3f8'),
        },
    ),
    'NEMO-CNRS': Submission(
        registration='8U2ZW',
        files={
            'ocean0': ('Ocean0_COM_NEMO-CNRS.nc', 'f78vz'),
            'ocean1': ('Ocean1_COM_NEMO-CNRS.nc', 'wdzqp'),
            'ocean2': ('Ocean2_COM_NEMO-CNRS.nc', 'hjrc5'),
        },
    ),
    'COCO': Submission(
        registration='JMCN7',
        files={
            'ocean0': ('Ocean0_COM_COCO.GT0025.nc', 'q36uf'),
            'ocean1': ('Ocean1_COM_COCO.nc', 'mdvz9'),
            'ocean2': ('Ocean2_COM_COCO.nc', 'ykb39'),
        },
    ),
    'MOM6-SIGMA-ZSTAR': Submission(
        registration='CMQP4',
        files={
            'ocean0': ('Ocean0_COM_MOM6_SIGMA_ZSTAR.nc', 'd2yh4'),
            'ocean1': ('Ocean1_COM_MOM6_SIGMA_ZSTAR.nc', '6rngq'),
            'ocean2': ('Ocean2_COM_MOM6_SIGMA_ZSTAR.nc', '58fg3'),
        },
    ),
    'MOM6': Submission(
        registration='K9TBC',
        files={
            'ocean0': ('Ocean0_COM_MOM6.nc', '680ba5be914ce3dfa625b12a'),
            'ocean1': ('Ocean1_COM_MOM6.nc', 'evh7g'),
            'ocean2': ('Ocean2_COM_MOM6.nc', '6qhdk'),
        },
    ),
    'MITgcm-JPL': Submission(
        registration='QNA89',
        files={
            'ocean0': ('Ocean0_yosi_COM_MITgcm_JPL_new.nc', 'umt9z'),
            'ocean1': ('Ocean1_yosi_COM_MITgcm_JPL_new.nc', 'cm98p'),
            'ocean2': ('Ocean2_yosi_COM_MITgcm_JPL_new.nc', 'dvw36'),
        },
    ),
    'NEMO-UKESM1is': Submission(
        registration='QMWRG',
        files={
            'ocean0': (
                'Ocean0_COM_NEMO-UKESM1is.nc',
                '680bb1e24b754df629568ba8',
            ),
            'ocean1': (
                'Ocean1_COM_NEMO-UKESM1is.nc',
                '680bb1e24b754df629568ba9',
            ),
            'ocean2': (
                'Ocean2_COM_NEMO-UKESM1is.nc',
                '680bb1e24b754df629568ba6',
            ),
        },
    ),
    'FVCOM': Submission(
        registration='VSHKM',
        files={
            'ocean0': ('Ocean0_COM_FVCOM.nc', '7prcg'),
            'ocean1': ('Ocean1_COM_FVCOM.nc', '7xkz2'),
            'ocean2': ('Ocean2_COM_FVCOM.nc', 'a78n9'),
        },
    ),
}

#: The experiments with published results
EXPERIMENTS = ['ocean0', 'ocean1', 'ocean2']

#: The file of every model's reduced results that the step writes
YUNG2026_FILENAME = 'yung2026.nc'

#: The time series read from each submission
SERIES = ['totalMeltFlux', 'meanMeltRate', 'meanTemperature', 'meanSalinity']

#: The maps averaged over the end of each submission
MAPS = ['meltRate', 'thermalDriving', 'frictionVelocity']


class Yung2026(Step):
    """
    A step that downloads every model's COM submission of one experiment
    into the ocean database and reduces it to the series, maps and
    strengths the comparisons plot

    Attributes
    ----------
    experiment : str
        The experiment, ``ocean0``, ``ocean1`` or ``ocean2``

    mean_months : int
        The number of months at the end of each submission that time means
        cover
    """

    def __init__(self, component, subdir, experiment, mean_months):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        experiment : str
            The experiment

        mean_months : int
            The number of months at the end of each submission that time
            means cover
        """
        super().__init__(
            component=component,
            name=f'yung2026_{experiment}',
            subdir=subdir,
            ntasks=1,
            cpus_per_task=1,
        )
        self.experiment = experiment
        self.mean_months = mean_months
        for model, submission in SUBMISSIONS.items():
            filename, identifier = submission.files[experiment]
            self.add_input_file(
                filename=f'{model}.nc',
                target=filename,
                database='yung2026',
                database_component='ocean',
                url=f'https://osf.io/download/{identifier}/',
            )
        self.add_output_file(filename=YUNG2026_FILENAME)

    def run(self):
        """
        Reduce every model's submission
        """
        reduced = [
            _reduce_submission(f'{model}.nc', self.mean_months)
            for model in SUBMISSIONS
        ]
        months = max(ds.sizes['nMonths'] for ds in reduced)
        reduced = [
            ds.pad(nMonths=(0, months - ds.sizes['nMonths'])) for ds in reduced
        ]
        ds = xr.concat(reduced, dim='nModels')
        ds.coords['time'] = ('nMonths', (np.arange(months) + 0.5) / 12.0)
        ds.coords['model'] = ('nModels', list(SUBMISSIONS))
        ds.attrs['citation'] = CITATION
        ds.attrs['registrations'] = ', '.join(
            f'{model}: https://doi.org/10.17605/OSF.IO/{submission.registration}'
            for model, submission in SUBMISSIONS.items()
        )
        ds.attrs['license'] = 'CC-BY 4.0'
        ds.attrs['mean_months'] = self.mean_months
        write_netcdf(ds, YUNG2026_FILENAME)
        with open('README', 'w') as readme:
            readme.write(
                f'ISOMIP+ COM results for {self.experiment}, from\n'
                f'{CITATION}\n\nLicense: CC-BY 4.0\n\n'
            )
            for model, submission in SUBMISSIONS.items():
                filename, _ = submission.files[self.experiment]
                readme.write(
                    f'{model}: {filename}, https://doi.org/10.17605/OSF.IO/'
                    f'{submission.registration}\n'
                )


def get_yung2026_step(component, config, experiment, mean_months):
    """
    Get the shared step with the published results of an experiment

    Parameters
    ----------
    component : polaris.Component
        The e3sm/analysis component

    config : polaris.config.PolarisConfigParser
        The config shared by the MISOMIP analysis tasks

    experiment : str
        The experiment, ``ocean0``, ``ocean1`` or ``ocean2``

    mean_months : int
        The number of months at the end of each submission that time means
        cover

    Returns
    -------
    step : polaris.tasks.e3sm.analysis.misomip.yung2026.Yung2026
        The step
    """
    return component.get_or_create_shared_step(
        step_cls=Yung2026,
        subdir=f'misomip/yung2026/{experiment}',
        config=config,
        config_filename='misomip_analysis.cfg',
        experiment=experiment,
        mean_months=mean_months,
    )


def _reduce_submission(filename, mean_months):
    """Reduce one model's submission to what the comparisons plot"""
    ds = xr.open_dataset(filename, decode_times=False)
    count = ds.sizes['nTime']
    ds_out = xr.Dataset()
    for name in SERIES:
        ds_out[name] = ('nMonths', _clean(_get(ds, name, (count,))))

    draft = _clean(ds.iceDraft.values)
    if draft.ndim == 3:
        draft = draft[-1]
    # one submission gives the draft as a positive depth
    if np.nanmax(draft) > 0.0 and np.nanmin(draft) >= 0.0:
        draft = -draft
    melt = _clean(ds.meltRate.values)
    deep = draft < -300.0
    ds_out['meanMeltRateDeep'] = (
        'nMonths',
        np.array([np.nanmean(month[deep]) for month in melt]),
    )

    end = slice(max(count - mean_months, 0), count)
    shape = melt.shape
    for name in MAPS:
        values = _clean(_get(ds, name, shape))
        ds_out[name] = (('ny', 'nx'), np.nanmean(values[end], 0))
    ds_out['iceDraft'] = (('ny', 'nx'), draft)

    ds_out['meltRateByDraft'] = (
        'nDraftBins',
        _bin_by(ds_out.meltRate.values, draft, DRAFT_EDGES),
    )
    ds_out.coords['draftBin'] = (
        'nDraftBins',
        0.5 * (DRAFT_EDGES[:-1] + DRAFT_EDGES[1:]),
    )

    bsf = _clean(_get(ds, 'barotropicStreamfunction', shape))
    bsf = np.nanmean(bsf[end], 0)
    ds_out['barotropicStrength'] = 1e-6 * _range(bsf[draft < 0.0])
    if 'overturningStreamfunction' in ds:
        osf = np.nanmean(_clean(ds.overturningStreamfunction.values[end]), 0)
        cavity = ds.x.values < ICE_FRONT_X
        ds_out['overturningStrength'] = 1e-6 * _range(osf[:, cavity])
    else:
        ds_out['overturningStrength'] = np.nan
    ds_out['meanMeltRateEnd'] = float(np.nanmean(ds_out.meanMeltRate[end]))
    return ds_out


def _get(ds, name, shape):
    """A variable's values, or NaN if the submission lacks it"""
    if name in ds:
        return ds[name].values
    return np.full(shape, np.nan)


def _clean(values):
    """Values as floats, with fill values that were not decoded as NaN"""
    values = np.asarray(values, dtype=float)
    return np.where(np.abs(values) > 1e30, np.nan, values)


def _range(values):
    """The range of finite values, or NaN if there are none"""
    if not np.any(np.isfinite(values)):
        return np.nan
    return float(np.nanmax(values) - np.nanmin(values))


def _bin_by(field, coord, edges):
    """The mean of a field in bins of a coordinate"""
    means = []
    for lower, upper in zip(edges[:-1], edges[1:], strict=True):
        in_bin = (coord >= lower) & (coord < upper) & np.isfinite(field)
        means.append(np.mean(field[in_bin]) if np.any(in_bin) else np.nan)
    return np.array(means)


def published_path(step):
    """The path to the reduced results of a Yung2026 step"""
    return os.path.join(step.path, YUNG2026_FILENAME)
