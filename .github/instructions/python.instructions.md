---
applyTo: "**/*.py"
---

# Python Instructions

- Keep lines at 79 characters or fewer whenever possible.
- Adhere to `ruff format` formatting.
- Keep imports at module scope whenever possible. Avoid local imports
  unless they are needed for circular-import avoidance or optional
  dependencies.
- Defer third-party packages that a module only uses inside functions with
  `polaris.lazy`: the real import under `if TYPE_CHECKING:` and
  `lazy_module()` or `lazy_attr()` in the `else` branch.  Running
  `utils/defer_imports/defer_imports.py` on a module does this.  Keep a
  third-party import eager only when its name is used while the module is
  imported.
- Avoid nested functions whenever possible.
- Prefer public functions before private helper functions whenever
  practical.
- Prefer private module-level helper functions over nested helpers.
