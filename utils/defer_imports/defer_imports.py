#!/usr/bin/env python3
"""
Defer the third-party imports of Polaris modules

Rewrites module-scope imports of third-party packages that a module only
uses inside functions into the deferred form from ``polaris.lazy``:

.. code-block:: python

    from typing import TYPE_CHECKING

    from polaris.lazy import lazy_attr, lazy_module

    if TYPE_CHECKING:
        import numpy as np
        from mpas_tools.io import write_netcdf
    else:
        np = lazy_module('numpy')
        write_netcdf = lazy_attr('mpas_tools.io', 'write_netcdf')

An ``import`` whose name is never used, made for its side effects (such as
``import cmocean`` to register colormaps), becomes
``lazy_side_effect('cmocean')``, which imports it when any other deferred
name in the module is first used.  A module with nothing else deferred keeps
it eager.

An import is left alone when its name is used while the module is being
imported: at module scope, in a class body, a decorator, a default value or a
base class.  When the only such uses are annotations, the module gains
``from __future__ import annotations`` so that they are no longer evaluated.

Run it from the root of the repository with the Polaris environment active,
then run pre-commit to sort the imports it adds:

.. code-block:: bash

    python utils/defer_imports/defer_imports.py polaris
    pre-commit run --all-files

It is safe to rerun: a module that is already converted keeps its deferred
imports and only new eager ones are converted.  After rebasing a branch onto
a version of Polaris that has been converted, take the branch's version of a
conflicting import block and run the script again.

``--check`` lists what would change without writing anything.
"""

import argparse
import ast
import importlib
import inspect
import os
import sys
import types
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# third-party packages that are fine to import eagerly
EAGER_PACKAGES = {'tranche'}

# typing names that are only ever evaluated by type checkers
TYPE_CHECKING_GUARD = 'TYPE_CHECKING'


@dataclass
class _Binding:
    """A name bound by a module-scope import"""

    name: str
    module: str
    attr: Optional[str]
    stmt: ast.stmt
    alias: ast.alias
    # imported only for its side effects: the name is never used
    side_effect: bool = False


@dataclass
class _Report:
    path: str
    converted: List[str] = field(default_factory=list)
    kept: List[Tuple[str, str]] = field(default_factory=list)
    future_annotations: bool = False


def main():
    parser = argparse.ArgumentParser(
        description='Defer the third-party imports of Polaris modules'
    )
    parser.add_argument(
        'paths', nargs='+', help='Python files or directories to convert'
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='List what would change without changing anything',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='Also list the imports that have to stay eager, and why',
    )
    args = parser.parse_args()

    changed = 0
    for path in _python_files(args.paths):
        report = convert_file(path, write=not args.check)
        if report.converted:
            changed += 1
            extra = (
                ' (+ from __future__ import annotations)'
                if report.future_annotations
                else ''
            )
            print(f'{path}: {", ".join(report.converted)}{extra}')
        if args.verbose:
            for name, reason in report.kept:
                print(f'{path}: kept {name}: {reason}')

    verb = 'would change' if args.check else 'changed'
    print(f'{changed} modules {verb}')
    if args.check and changed > 0:
        sys.exit(1)


def convert_file(path: str, write: bool = True) -> _Report:
    """
    Defer the third-party imports of one module

    Parameters
    ----------
    path : str
        The path to the module

    write : bool, optional
        Whether to write the converted module back

    Returns
    -------
    report : _Report
        What was converted and what was kept
    """
    with open(path) as f:
        source = f.read()
    tree = ast.parse(source)
    report = _Report(path=path)

    bindings = _deferrable_bindings(tree, report)
    if not bindings:
        return report

    has_future = _has_future_annotations(tree)
    eager_uses, annotation_uses = _import_time_uses(tree, has_future)

    to_convert: List[_Binding] = []
    needs_future = False
    used_names = _used_names(tree)
    for binding in bindings:
        binding.side_effect = (
            binding.attr is None and binding.name not in used_names
        )
        if binding.name in eager_uses:
            report.kept.append((binding.name, 'used while importing'))
            continue
        reason = _not_proxyable(binding)
        if reason is not None:
            report.kept.append((binding.name, reason))
            continue
        if binding.name in annotation_uses:
            needs_future = True
        to_convert.append(binding)

    has_proxies = any(not binding.side_effect for binding in to_convert) or (
        _has_existing_proxies(tree)
    )
    if not has_proxies:
        for binding in to_convert:
            report.kept.append(
                (
                    binding.name,
                    'imported for its side effects, and nothing else in the '
                    'module is deferred',
                )
            )
        to_convert = []

    if not to_convert:
        return report

    report.converted = [binding.name for binding in to_convert]
    report.future_annotations = needs_future and not has_future
    if write:
        new_source = _rewrite(source, tree, to_convert, needs_future)
        # make sure the result still parses
        ast.parse(new_source)
        with open(path, 'w') as f:
            f.write(new_source)
    return report


def _python_files(paths: List[str]) -> List[str]:
    files = []
    for path in paths:
        if os.path.isdir(path):
            for root, dirs, names in os.walk(path):
                dirs[:] = sorted(d for d in dirs if d != '__pycache__')
                for name in sorted(names):
                    if name.endswith('.py'):
                        files.append(os.path.join(root, name))
        else:
            files.append(path)
    # polaris.lazy can't defer its own imports
    return [f for f in files if os.path.basename(f) != 'lazy.py']


def _used_names(tree: ast.Module) -> Set[str]:
    """Every name that is loaded anywhere in the module"""
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def _has_existing_proxies(tree: ast.Module) -> bool:
    """Whether the module already binds a name with a deferred import"""
    existing = _existing_type_checking_block(tree)
    if existing is None:
        return False
    return any(isinstance(stmt, ast.Assign) for stmt in existing.orelse)


def _is_third_party(module: str) -> bool:
    root = module.split('.')[0]
    return (
        root not in sys.stdlib_module_names
        and root != 'polaris'
        and root not in EAGER_PACKAGES
        and root != '__future__'
    )


def _deferrable_bindings(tree: ast.Module, report: _Report) -> List[_Binding]:
    """The names bound by module-scope imports of third-party packages"""
    bindings = []
    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                if not _is_third_party(alias.name):
                    continue
                if alias.asname is None and '.' in alias.name:
                    report.kept.append(
                        (alias.name, 'dotted import without an alias')
                    )
                    continue
                name = alias.asname or alias.name
                bindings.append(_Binding(name, alias.name, None, stmt, alias))
        elif isinstance(stmt, ast.ImportFrom):
            if stmt.level != 0 or stmt.module is None:
                continue
            if not _is_third_party(stmt.module):
                continue
            for alias in stmt.names:
                if alias.name == '*':
                    report.kept.append((stmt.module, 'star import'))
                    continue
                name = alias.asname or alias.name
                bindings.append(
                    _Binding(name, stmt.module, alias.name, stmt, alias)
                )
    return bindings


def _has_future_annotations(tree: ast.Module) -> bool:
    for stmt in tree.body:
        if (
            isinstance(stmt, ast.ImportFrom)
            and stmt.module == '__future__'
            and any(alias.name == 'annotations' for alias in stmt.names)
        ):
            return True
    return False


def _import_time_uses(
    tree: ast.Module, has_future: bool
) -> Tuple[Set[str], Set[str]]:
    """
    The names that are evaluated while the module is imported, other than in
    annotations, and the names that are evaluated only in annotations
    """
    collector = _ImportTimeCollector(has_future)
    for stmt in tree.body:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            continue
        collector.visit(stmt)
    return collector.eager, collector.annotations - collector.eager


class _ImportTimeCollector(ast.NodeVisitor):
    """
    Collect the names that are loaded while a module is being imported

    Function bodies and lambdas run later and are skipped; their decorators,
    defaults and (unless annotations are postponed) annotations are not.
    """

    def __init__(self, has_future: bool):
        self.has_future = has_future
        self.eager: Set[str] = set()
        self.annotations: Set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.eager.add(node.id)

    def visit_If(self, node: ast.If) -> None:
        if _is_type_checking(node.test):
            # only the else branch runs
            for stmt in node.orelse:
                self.visit(stmt)
            return
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in node.args.defaults + node.args.kw_defaults:
            if default is not None:
                self.visit(default)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._annotation(node.annotation)
        if node.value is not None:
            self.visit(node.value)
        self.visit(node.target)

    def _visit_function(self, node) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        args = node.args
        for default in args.defaults + args.kw_defaults:
            if default is not None:
                self.visit(default)
        for arg in args.posonlyargs + args.args + args.kwonlyargs:
            self._annotation(arg.annotation)
        for arg in (args.vararg, args.kwarg):
            if arg is not None:
                self._annotation(arg.annotation)
        self._annotation(node.returns)

    def _annotation(self, node: Optional[ast.expr]) -> None:
        if node is None or self.has_future:
            return
        names = {
            child.id for child in ast.walk(node) if isinstance(child, ast.Name)
        }
        self.annotations.update(names)


def _is_type_checking(test: ast.expr) -> bool:
    if isinstance(test, ast.Name):
        return test.id == TYPE_CHECKING_GUARD
    if isinstance(test, ast.Attribute):
        return test.attr == TYPE_CHECKING_GUARD
    return False


def _not_proxyable(binding: _Binding) -> Optional[str]:
    """
    Why a name can't be replaced by a proxy, or None if it can

    A proxy forwards calls, attribute lookups and isinstance() checks, so it
    can stand in for a module, function or class but not for a constant.
    """
    if binding.attr is None:
        return None
    try:
        module = importlib.import_module(binding.module)
    except Exception as e:
        return f'could not import {binding.module}: {e}'
    try:
        value = getattr(module, binding.attr)
    except AttributeError:
        try:
            importlib.import_module(f'{binding.module}.{binding.attr}')
        except Exception:
            return f'{binding.attr} not found in {binding.module}'
        return None
    if isinstance(value, types.ModuleType) or inspect.isclass(value):
        return None
    if callable(value):
        return None
    return f'{type(value).__name__} is not a module, class or function'


def _rewrite(
    source: str,
    tree: ast.Module,
    to_convert: List[_Binding],
    needs_future: bool,
) -> str:
    lines = source.splitlines(keepends=True)
    converted_aliases = {id(binding.alias) for binding in to_convert}

    # replace each affected import statement with what is left of it
    edits: Dict[int, Tuple[int, str]] = dict()
    affected: List[ast.stmt] = []
    for binding in to_convert:
        if binding.stmt not in affected:
            affected.append(binding.stmt)
    for stmt in affected:
        assert isinstance(stmt, (ast.Import, ast.ImportFrom))
        assert stmt.end_lineno is not None
        remaining = [
            alias for alias in stmt.names if id(alias) not in converted_aliases
        ]
        if remaining:
            if isinstance(stmt, ast.Import):
                new_stmt: ast.stmt = ast.Import(names=remaining)
            else:
                assert isinstance(stmt, ast.ImportFrom)
                new_stmt = ast.ImportFrom(
                    module=stmt.module, names=remaining, level=0
                )
            replacement = ast.unparse(new_stmt) + '\n'
        else:
            replacement = ''
        edits[stmt.lineno] = (stmt.end_lineno, replacement)

    # an existing deferred block is merged into the new one
    existing = _existing_type_checking_block(tree)
    if existing is not None:
        assert existing.end_lineno is not None
        edits[existing.lineno] = (existing.end_lineno, '')

    # the deferred block goes after the last module-scope import
    last_import = max(
        stmt.end_lineno
        for stmt in tree.body
        if isinstance(stmt, (ast.Import, ast.ImportFrom))
        and stmt.end_lineno is not None
    )
    block = _deferred_block(lines, tree, to_convert)

    out: List[str] = []
    lineno = 1
    while lineno <= len(lines):
        if lineno in edits:
            end, replacement = edits[lineno]
            out.append(replacement)
            if end >= last_import and lineno <= last_import:
                out.append(block)
            lineno = end + 1
            continue
        out.append(lines[lineno - 1])
        if lineno == last_import:
            out.append(block)
        lineno += 1

    new_source = ''.join(out)
    header = _header_imports(tree, to_convert, needs_future)
    return _insert_header(new_source, header)


def _deferred_block(
    lines: List[str], tree: ast.Module, to_convert: List[_Binding]
) -> str:
    """
    The ``if TYPE_CHECKING`` block that binds the converted names, merged
    with the module's existing one if it has one
    """
    checked: List[str] = []
    deferred: List[str] = []
    existing = _existing_type_checking_block(tree)
    if existing is not None:
        # keep the existing statements as written, comments and all
        checked.extend(_statement_lines(lines, existing.body))
        deferred.extend(_statement_lines(lines, existing.orelse))

    for binding in to_convert:
        alias = ast.alias(name=binding.alias.name, asname=binding.alias.asname)
        if binding.side_effect:
            checked.append(f'    import {binding.alias.name}  # noqa: F401\n')
            deferred.append(f'    lazy_side_effect({binding.module!r})\n')
            continue
        if binding.attr is None:
            stmt: ast.stmt = ast.Import(names=[alias])
            deferred.append(
                f'    {binding.name} = lazy_module({binding.module!r})\n'
            )
        else:
            stmt = ast.ImportFrom(
                module=binding.module, names=[alias], level=0
            )
            deferred.append(
                f'    {binding.name} = lazy_attr({binding.module!r}, '
                f'{binding.attr!r})\n'
            )
        checked.append(f'    {ast.unparse(stmt)}\n')

    return (
        '\nif TYPE_CHECKING:\n'
        + ''.join(checked)
        + 'else:\n'
        + ''.join(deferred)
        + '\n'
    )


def _statement_lines(lines: List[str], stmts: List[ast.stmt]) -> List[str]:
    result = []
    for stmt in stmts:
        assert stmt.end_lineno is not None
        result.extend(lines[stmt.lineno - 1 : stmt.end_lineno])
    return result


def _existing_type_checking_block(tree: ast.Module) -> Optional[ast.If]:
    for stmt in tree.body:
        if isinstance(stmt, ast.If) and _is_type_checking(stmt.test):
            return stmt
    return None


def _header_imports(
    tree: ast.Module, to_convert: List[_Binding], needs_future: bool
) -> List[str]:
    """The imports the deferred block needs that the module lacks"""
    have_future = _has_future_annotations(tree)
    have_type_checking = False
    have_lazy: Set[str] = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.ImportFrom) and stmt.module == 'typing':
            if any(alias.name == TYPE_CHECKING_GUARD for alias in stmt.names):
                have_type_checking = True
        if isinstance(stmt, ast.ImportFrom) and stmt.module == 'polaris.lazy':
            have_lazy.update(alias.name for alias in stmt.names)

    header = []
    if needs_future and not have_future:
        header.append('from __future__ import annotations\n')
    if not have_type_checking:
        header.append(f'from typing import {TYPE_CHECKING_GUARD}\n')
    needed = set()
    for binding in to_convert:
        if binding.side_effect:
            needed.add('lazy_side_effect')
        elif binding.attr is None:
            needed.add('lazy_module')
        else:
            needed.add('lazy_attr')
    missing = sorted(needed - have_lazy)
    if missing:
        header.append(f'from polaris.lazy import {", ".join(missing)}\n')
    return header


def _insert_header(source: str, header: List[str]) -> str:
    """
    Insert imports after the docstring and any ``from __future__`` imports
    """
    if not header:
        return source
    tree = ast.parse(source)
    insert_after = 0
    for index, stmt in enumerate(tree.body):
        is_docstring = (
            index == 0
            and isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
            and isinstance(stmt.value.value, str)
        )
        is_future = (
            isinstance(stmt, ast.ImportFrom) and stmt.module == '__future__'
        )
        if is_docstring or is_future:
            assert stmt.end_lineno is not None
            insert_after = stmt.end_lineno
        else:
            break

    lines = source.splitlines(keepends=True)
    future = [line for line in header if line.startswith('from __future__')]
    others = [line for line in header if line not in future]
    text = ''.join(future) + ''.join(others)
    if insert_after > 0:
        text = '\n' + text
    return ''.join(lines[:insert_after]) + text + ''.join(lines[insert_after:])


if __name__ == '__main__':
    main()
