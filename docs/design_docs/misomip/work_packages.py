"""
Status of the MISOMIP work packages and the first stage that needs each.

Regenerate with any Python that has matplotlib:

    python work_packages.py work_packages.svg

To update, edit STATUS_DATE and ROWS. Each row is
(package, what it delivers, where the work is, status, first stage, note):
status is a key of STATUS; the first stage is an index into STAGES
(0 = A ... 3 = D), or None if no stage needs the package, in which case the
note is shown instead. Stage needs follow the "Order" table of the design.
"""

import sys

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch

STATUS_DATE = '2026-10-29'

SURFACE = '#fcfcfb'
INK = '#0b0b0b'
INK2 = '#52514e'
MUTED = '#898781'
LINE = '#c3c2b7'
STAGE = '#2a78d6'

# status: (label, fill, edge)
STATUS = {
    'review': ('PR open, tested', '#deebff', '#4c9aff'),
    'draft': ('draft PR, tested', '#e8e8e4', '#898781'),
    'hold': ('on hold', '#fff4d6', '#c98500'),
    'started': ('in progress, no PR', '#ffffff', '#4c9aff'),
    'none': ('not started', '#ffffff', '#c3c2b7'),
}

ROWS = [
    ('WP0', 'FAnSSIE branch + Polaris submodule',
     'branch live since Oct 16; polaris #842', 'review', 0, ''),
    ('WP1', 'Standalone ISOMIP+ Ocean0–2 and thin-film tasks',
     'polaris #826, #844', 'review', 1, ''),
    ('WP2', 'Split-explicit wetting and drying with a thin film',
     "E3SM-O-D #144 awaits Carolyn's review; polaris #861", 'hold', None,
     'none waits; RK4 until it lands'),
    ('WP3', 'Landice component: MALI + Albany in Polaris',
     'polaris #871; E3SM-O-D #151 merged', 'draft', 3, ''),
    ('WP4', 'MISMIP+ spin-up with MALI',
     'branch add-mismip-plus, on #871', 'started', 3, ''),
    ('WP5', 'MALI and ocean meshes, coupler maps', '', 'none', 1, ''),
    ('WP6', 'E3SM inputs: initial conditions, partitions, cases', '',
     'none', 1, ''),
    ('WP7', 'Idealized E3SM cases (no atmosphere, namelists)', '', 'none',
     1, ''),
    ('WP8', 'Moving grounding line in coupled runs', '', 'none', 2, ''),
    ('WP9', 'Analysis of the E3SM runs', '', 'none', 1, ''),
    ('WP10', 'Subgrid wetting and drying (optional)', '', 'none', None,
     'no stage needs it'),
    ('WP11', "E3SM's physics in ISOMIP+ (+ COM variants)",
     'E3SM-O-D #145–#150 merged; polaris #862', 'draft', 1, ''),
]

STAGES = [
    ('A', '4 km Ocean0\nprototype'),
    ('B', 'Ocean0–2\nin E3SM'),
    ('C', 'Ocean3–4\n(moving GL)'),
    ('D', 'IceOcean1r/1ra\n(MALI evolves)'),
]


def main():
    out = sys.argv[1]
    fig = plt.figure(figsize=(12, 6.6), facecolor=SURFACE)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 120)
    ax.set_ylim(0, 66)
    ax.axis('off')

    ax.text(1.5, 63.5, 'MISOMIP in E3SM: twelve work packages',
            fontsize=14, color=INK, va='center')
    ax.text(
        1.5, 60.6,
        f'Status as of {STATUS_DATE}. A dot marks the first stage that '
        'needs a package; the line shows it is needed from there on.',
        fontsize=10, color=INK2, va='center')

    stage_x = [83.5, 93, 102.5, 112]
    header_y = 55.5
    for x, (letter, desc) in zip(stage_x, STAGES):
        ax.text(x, header_y + 1.6, f'Stage {letter}', ha='center',
                va='center', fontsize=10.5, color=INK, weight='bold')
        ax.text(x, header_y - 1.4, desc, ha='center', va='center',
                fontsize=8.5, color=INK2, linespacing=1.1)

    row_h = 4.0
    top = 50.5
    for i, (wp, what, where, status, stage, note) in enumerate(ROWS):
        y = top - i * row_h
        if i % 2 == 0:
            ax.add_patch(FancyBboxPatch(
                (0.8, y - row_h / 2 + 0.25), 118.4, row_h - 0.5,
                boxstyle='round,pad=0,rounding_size=0.6', fc='#f4f5f2',
                ec='none'))
        ax.text(2, y, wp, fontsize=10.5, color=INK, weight='bold',
                va='center')
        ax.text(8, y + (0.8 if where else 0), what, fontsize=10.5,
                color=INK, va='center')
        if where:
            ax.text(8, y - 1.0, where, fontsize=8.5, color=INK2,
                    va='center')
        label, fill, edge = STATUS[status]
        ax.add_patch(FancyBboxPatch(
            (56, y - 1.2), 20, 2.4,
            boxstyle='round,pad=0,rounding_size=1.0', fc=fill, ec=edge,
            lw=1))
        ax.text(66, y, label, ha='center', va='center', fontsize=9.5,
                color=INK)
        if stage is None:
            ax.text(stage_x[0] - 3, y, note, fontsize=9, color=MUTED,
                    va='center')
            continue
        ax.plot([stage_x[stage], stage_x[-1]], [y, y], color=STAGE, lw=2,
                alpha=0.35, solid_capstyle='round')
        ax.add_patch(Circle((stage_x[stage], y), 0.9, fc=STAGE,
                            ec=SURFACE, lw=2, zorder=3))

    ax.plot([0.8, 119.2], [top + row_h / 2 + 0.6] * 2, color=LINE, lw=0.8)
    fig.savefig(out, dpi=180, facecolor=SURFACE)


if __name__ == '__main__':
    main()
