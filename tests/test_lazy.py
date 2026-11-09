import pickle
import subprocess
import sys
import textwrap

from polaris.lazy import lazy_attr, lazy_module


def test_lazy_module_imports_on_first_use():
    """A deferred module is not imported until an attribute is used"""
    out = _run(
        """
        import sys
        from polaris.lazy import lazy_module
        json_mod = lazy_module('json.tool')
        print('json.tool' in sys.modules)
        json_mod.main
        print('json.tool' in sys.modules)
        """
    )
    assert out == ['False', 'True']


def test_proxy_replaces_itself_in_its_namespace():
    """After first use, the bound name refers to the real module"""
    out = _run(
        """
        import types
        from polaris.lazy import lazy_attr, lazy_module
        colorsys = lazy_module('colorsys')
        dedent = lazy_attr('textwrap', 'dedent')
        colorsys.rgb_to_hsv(0.0, 0.0, 0.0)
        dedent('  x')
        print(isinstance(colorsys, types.ModuleType))
        print(type(dedent).__name__)
        """
    )
    assert out == ['True', 'function']


def test_lazy_attr_calls_and_checks_instances():
    """A deferred class can be called and used in isinstance()"""
    ordered_dict = lazy_attr('collections', 'OrderedDict')
    instance = ordered_dict(a=1)
    assert instance['a'] == 1
    assert isinstance(instance, ordered_dict)
    assert issubclass(type(instance), ordered_dict)


def test_lazy_attr_imports_submodules():
    """``lazy_attr(package, submodule)`` imports the submodule"""
    parse = lazy_attr('xml.dom', 'minidom')
    assert parse.parseString('<a/>').documentElement.tagName == 'a'


def test_lazy_module_forwards_setattr():
    """Setting an attribute on a deferred module sets it on the module"""
    out = _run(
        """
        import sys
        from polaris.lazy import lazy_module
        mod = lazy_module('polaris.version')
        mod.polaris_lazy_test_value = 3
        print(sys.modules['polaris.version'].polaris_lazy_test_value)
        """
    )
    assert out == ['3']


def test_lazy_attr_pickles_as_the_real_object():
    """Pickling a deferred function pickles the function by reference"""
    dedent = lazy_attr('textwrap', 'dedent')
    assert pickle.loads(pickle.dumps(dedent)) is textwrap.dedent


def test_load_all_imports_everything_deferred():
    out = _run(
        """
        import sys
        from polaris.lazy import lazy_module, lazy_side_effect, load_all
        mod = lazy_module('json.tool')
        lazy_side_effect('xml.dom.minidom')
        load_all()
        print('json.tool' in sys.modules)
        print('xml.dom.minidom' in sys.modules)
        """
    )
    assert out == ['True', 'True']


def test_lazy_module_repr_names_the_module():
    assert repr(lazy_module('os.path')) == '<deferred os.path>'


def test_side_effect_import_waits_for_a_deferred_name():
    """A side-effect import runs when the module first uses a deferred name"""
    out = _run(
        """
        import sys
        from polaris.lazy import lazy_module, lazy_side_effect
        lazy_side_effect('json.tool')
        colorsys = lazy_module('colorsys')
        print('json.tool' in sys.modules)
        colorsys.rgb_to_hsv(0.0, 0.0, 0.0)
        print('json.tool' in sys.modules)
        """
    )
    assert out == ['False', 'True']


def _run(code):
    result = subprocess.run(
        [sys.executable, '-c', textwrap.dedent(code)],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.split()
