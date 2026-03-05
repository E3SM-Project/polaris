# OMEGA Cron Scripts

Automated cron job scripts for continuous testing and CDash reporting of OMEGA ocean modeling projects across multiple HPC systems.

## Overview

This repository orchestrates the compilation, testing, and result submission to [CDash](https://my.cdash.org) for two major OMEGA ocean model components:

- **Omega** - Next-generation ocean model
- **Polaris** - MPAS-Ocean model with Omega integration

## Supported Systems

| Machine | Location | Compilers |
|---------|----------|-----------|
| Frontier | ORNL | craygnu, craycray, crayamd (with mphipcc variants) |
| Chrysalis | ANL (LCRC) | gnu, intel |
| pm-gpu | NERSC (Perlmutter GPU) | gnugpu |
| pm-cpu | NERSC (Perlmutter CPU) | gnu |

## Repository Structure

```
cron-scripts/
├── launch_all.sh              # Main entry point
├── machines/                  # Machine-specific configurations
│   ├── config_machine.sh      # Auto-detection dispatcher
│   ├── config_frontier.sh
│   ├── config_chrysalis.sh
│   ├── config_pm-gpu.sh
│   └── config_pm-cpu.sh
└── tasks/                     # Scheduled job definitions
    ├── omega_cdash/           # Omega model CDash testing
    │   ├── launch_omega_cdash.sh
    │   └── job_*.sbatch
    └── polaris_cdash/         # Polaris model CDash testing
        ├── launch_polaris_ctest.sh
        ├── polaris_cdash.py
        └── CTestScript.txt
```

## Usage

### Run on auto-detected machine

```bash
./launch_all.sh
```

### Run on a specific machine

```bash
./launch_all.sh -m frontier
./launch_all.sh -m chrysalis
./launch_all.sh -m pm-gpu
./launch_all.sh -m pm-cpu
```

### Set up in crontab

```bash
# Run daily at 1 AM
0 1 * * * /path/to/cron-scripts/launch_all.sh
```

## How It Works

1. `launch_all.sh` auto-detects the machine via hostname or accepts a `-m` flag
2. Sources the appropriate machine configuration (compilers, paths, modules)
3. Uses file locking to prevent concurrent executions
4. Discovers and executes all `launch*.sh` scripts in task subdirectories
5. Each task clones/updates repos, submits SBATCH jobs, and reports to CDash

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CRONJOB_BASEDIR` | Root directory for job outputs |
| `CRONJOB_MACHINE` | Detected/specified machine name |
| `CRONJOB_LOGDIR` | Log directory location |
| `E3SM_COMPILERS` | Space-separated list of compilers to test |

## Adding a New Machine

1. Create `machines/config_<machine>.sh` with:
   - `CRONJOB_BASEDIR` path
   - `E3SM_COMPILERS` list
   - Module loads and environment setup
2. Add hostname pattern to `machines/config_machine.sh`
3. Create machine-specific SBATCH scripts in task directories if needed

## Adding a New Task

1. Create a new directory under `tasks/`
2. Add a `launch_<taskname>.sh` script
3. The script will be auto-discovered and executed by `launch_all.sh`

## CDash Integration

Test results are submitted to:
- E3SM project: https://my.cdash.org/submit.php?project=E3SM
- Omega project: https://my.cdash.org/submit.php?project=omega
