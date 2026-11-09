"""
Deferred imports that keep their declarations

A module that uses a heavy package only inside functions binds it with
:py:func:`lazy_module` or :py:func:`lazy_attr`, keeping the real import
under ``if TYPE_CHECKING`` so that mypy and IDEs still see it:

.. code-block:: python

    from typing import TYPE_CHECKING

    from polaris.lazy import lazy_attr, lazy_module

    if TYPE_CHECKING:
        import numpy as np
        from mpas_tools.io import write_netcdf
    else:
        np = lazy_module('numpy')
        write_netcdf = lazy_attr('mpas_tools.io', 'write_netcdf')

The package is imported the first time the name is used.  At that point the
proxy replaces itself in the namespace that bound it with the real module or
attribute, so later uses cost nothing and see the real object.
"""

import importlib
import sys
from typing import Any, Dict, List, Optional

__all__ = ['lazy_attr', 'lazy_module', 'load_all']


def lazy_module(name: str) -> Any:
    """
    A proxy for a module that is imported on first use

    Parameters
    ----------
    name : str
        The full name of the module, e.g. ``'numpy'`` or
        ``'matplotlib.pyplot'``

    Returns
    -------
    proxy : object
        A stand-in for the module that imports it on first attribute access
    """
    return _register(_LazyModule(name, None, _caller_globals()))


def lazy_attr(module: str, attr: str) -> Any:
    """
    A proxy for a function, class or submodule that is imported on first use

    Parameters
    ----------
    module : str
        The full name of the module the attribute comes from

    attr : str
        The name of the attribute, which may also be a submodule of
        ``module``

    Returns
    -------
    proxy : object
        A stand-in for the attribute that imports its module when it is
        called, has an attribute looked up or is used in ``isinstance()``
    """
    return _register(_LazyAttr(module, attr, _caller_globals()))


def load_all() -> None:
    """
    Import everything that has been deferred so far

    A process that forks workers calls this first, so that each package is
    imported once in the parent rather than once in every child.
    """
    for proxy in list(_proxies):
        proxy._polaris_lazy_resolve()


_proxies: List['_LazyBase'] = []


def _register(proxy: '_LazyBase') -> '_LazyBase':
    _proxies.append(proxy)
    return proxy


def _caller_globals() -> Optional[Dict[str, Any]]:
    """The globals of the module that called lazy_module() or lazy_attr()"""
    try:
        # 0 is this function, 1 is lazy_module() or lazy_attr()
        return sys._getframe(2).f_globals
    except ValueError:
        return None


class _LazyBase:
    """
    The shared machinery of the module and attribute proxies
    """

    __slots__ = ('_polaris_lazy_target', '_polaris_lazy_namespace', '_attr')

    def __init__(
        self,
        module: str,
        attr: Optional[str],
        namespace: Optional[Dict[str, Any]],
    ):
        object.__setattr__(self, '_polaris_lazy_target', None)
        object.__setattr__(self, '_polaris_lazy_namespace', namespace)
        object.__setattr__(self, '_attr', (module, attr))

    def _polaris_lazy_resolve(self) -> Any:
        target = object.__getattribute__(self, '_polaris_lazy_target')
        if target is not None:
            return target
        module_name, attr = object.__getattribute__(self, '_attr')
        target = importlib.import_module(module_name)
        if attr is not None:
            target = _get_attr(target, module_name, attr)
        object.__setattr__(self, '_polaris_lazy_target', target)
        _replace_in_namespace(self, target)
        return target

    def __getattr__(self, name: str) -> Any:
        return getattr(self._polaris_lazy_resolve(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._polaris_lazy_resolve(), name, value)

    def __dir__(self) -> List[str]:
        return dir(self._polaris_lazy_resolve())

    def __repr__(self) -> str:
        module_name, attr = object.__getattribute__(self, '_attr')
        name = module_name if attr is None else f'{module_name}.{attr}'
        return f'<deferred {name}>'

    def __reduce__(self) -> Any:
        # pickle the real object, which pickle stores by reference
        return _resolve_for_pickle, (object.__getattribute__(self, '_attr'),)


class _LazyModule(_LazyBase):
    """
    A module that is imported on first attribute access
    """

    __slots__ = ()


class _LazyAttr(_LazyBase):
    """
    A function, class or submodule that is imported on first use
    """

    __slots__ = ()

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._polaris_lazy_resolve()(*args, **kwargs)

    def __instancecheck__(self, instance: Any) -> bool:
        return isinstance(instance, self._polaris_lazy_resolve())

    def __subclasscheck__(self, subclass: Any) -> bool:
        return issubclass(subclass, self._polaris_lazy_resolve())

    def __getitem__(self, key: Any) -> Any:
        return self._polaris_lazy_resolve()[key]


def _get_attr(module: Any, module_name: str, attr: str) -> Any:
    """
    An attribute of a module, importing it as a submodule if it is not yet
    an attribute, as ``from module import attr`` does
    """
    try:
        return getattr(module, attr)
    except AttributeError:
        return importlib.import_module(f'{module_name}.{attr}')


def _replace_in_namespace(proxy: _LazyBase, target: Any) -> None:
    """
    Rebind every name in the proxy's home namespace that refers to the proxy
    """
    namespace = object.__getattribute__(proxy, '_polaris_lazy_namespace')
    if namespace is None:
        return
    for name, value in list(namespace.items()):
        if value is proxy:
            namespace[name] = target


def _resolve_for_pickle(spec: Any) -> Any:
    module_name, attr = spec
    target = importlib.import_module(module_name)
    if attr is not None:
        target = _get_attr(target, module_name, attr)
    return target
