import argparse
import json
import os
import pickle
import shutil
import sys
from datetime import datetime
from typing import Dict, List

from polaris import Step
from polaris.config import PolarisConfigParser
from polaris.io import imp_res


def update_cache(step_paths, date_string=None, dry_run=False):
    """
    Cache one or more polaris output files for use in a cached variant of the
    test case or step

    Parameters
    ----------
    step_paths : list of str
        The relative path of the original (uncached) steps from the base work
        directory

    date_string : str, optional
        The datestamp (YYMMDD) to use on the files.  Default is today's date.

    dry_run : bool, optional
        Whether this is a dry run (producing the json file but not copying
        files to the LCRC server)
    """
    if 'POLARIS_MACHINE' not in os.environ:
        machine = None
        invalid = True
    else:
        machine = os.environ['POLARIS_MACHINE']
        invalid = machine not in ['anvil', 'chrysalis']

    if invalid:
        raise ValueError('You must cache files from either Anvil or Chrysalis')

    config = PolarisConfigParser()
    config.add_from_package('polaris.machines', f'{machine}.cfg')

    if date_string is None:
        date_string = datetime.now().strftime("%y%m%d")

    # make a dictionary with components as keys, and lists of steps as values
    steps: Dict[str, List[Step]] = dict()
    for path in step_paths:
        with open(f'{path}/step.pickle', 'rb') as handle:
            _, step = pickle.load(handle)

        component = step.component.name

        if component in steps:
            steps[component].append(step)
        else:
            steps[component] = [step]

    # now, iterate over cores and steps
    for component in steps:
        database_root = config.get('paths', 'database_root')
        cache_root = f'{database_root}/{component}/polaris_cache'

        package = f'polaris.{component}'
        try:
            with open(f'{component}_cached_files.json') as data_file:
                cached_files = json.load(data_file)
        except FileNotFoundError:
            # we don't have a local version of the file yet, let's see if
            # there's a remote one for this component
            try:
                pkg_file = imp_res.files(package).joinpath('cached_files.json')
                with pkg_file.open('r') as data_file:
                    cached_files = json.load(data_file)
            except FileNotFoundError:
                # no cached files yet for this core
                cached_files = dict()

        for step in steps[component]:
            # load the step from its pickle file

            step_path = step.path

            for output in step.outputs:
                output = os.path.basename(output)
                out_filename = os.path.join(step_path, output)
                # remove the component from the file path
                target = out_filename[len(component) + 1:]
                path, ext = os.path.splitext(target)
                target = f'{path}.{date_string}{ext}'
                cached_files[out_filename] = target

                print(out_filename)
                print(f'  ==> {target}')
                output_path = f'{cache_root}/{target}'
                print(f'  copy to: {output_path}')
                print()
                if not dry_run:
                    directory = os.path.dirname(output_path)
                    try:
                        os.makedirs(directory)
                    except FileExistsError:
                        pass
                    shutil.copyfile(out_filename, output_path)

        out_filename = f'{component}_cached_files.json'
        with open(out_filename, 'w') as data_file:
            json.dump(cached_files, data_file, indent=4)


def main():
    parser = argparse.ArgumentParser(
        description='Cache the output files from one or more steps for use in '
                    'a cached variant of the step',
        prog='polaris cache')
    parser.add_argument("-i", "--orig_steps", nargs='+', dest="orig_steps",
                        type=str,
                        help="The relative path of the original (uncached) "
                             "steps from the base work directory",
                        metavar="STEP")
    parser.add_argument("-d", "--date_string", dest="date_string", type=str,
                        help="The datestamp (YYMMDD) to use on the files.  "
                             "Default is today's date.",
                        metavar="DATE")
    parser.add_argument("-r", "--dry_run", dest="dry_run",
                        help="Whether this is a dry run (producing the json "
                             "file but not copying files to the LCRC server).",
                        action="store_true")

    args = parser.parse_args(sys.argv[2:])
    update_cache(step_paths=args.orig_steps, date_string=args.date_string,
                 dry_run=args.dry_run)
