"""
Pipeline registry — discovers and loads pipeline classes from the `pipelines/` directory.

Pipelines are stored on the filesystem (like strategies) with three-tier ownership:
  pipelines/_shared/   — available to all users
  pipelines/_admin/    — admin-only
  pipelines/{user_id}/ — user-specific

Each pipeline directory must contain an __init__.py that defines a class
extending Pipeline.
"""
import os
import sys
import importlib
import importlib.util
import inspect

from qengine.framework.base import Pipeline, PipelineStack

PIPELINES_BASE = 'pipelines'
_REGISTRY: dict[str, type] = {}
_discovered = False


def _discover_pipelines() -> None:
    """
    Walk the pipelines/ directory tree and register all Pipeline subclasses.
    Called lazily on first access.
    """
    global _discovered
    if _discovered:
        return
    _discovered = True

    base = os.path.abspath(PIPELINES_BASE)
    if not os.path.isdir(base):
        return

    for subdir in os.listdir(base):
        subdir_path = os.path.join(base, subdir)
        if not os.path.isdir(subdir_path) or subdir.startswith('.') or subdir.startswith('__'):
            continue

        for pipeline_name in os.listdir(subdir_path):
            pipeline_path = os.path.join(subdir_path, pipeline_name)
            init_path = os.path.join(pipeline_path, '__init__.py')
            if not os.path.isdir(pipeline_path) or not os.path.isfile(init_path):
                continue
            if pipeline_name.startswith('.') or pipeline_name.startswith('__'):
                continue

            _load_pipeline(pipeline_name, subdir, init_path)


def _load_pipeline(pipeline_name: str, subdir: str, init_path: str) -> None:
    """Import a pipeline module from its file path and register any Pipeline subclass found."""
    module_name = f'pipelines.{subdir}.{pipeline_name}'
    try:
        if module_name in sys.modules:
            module = sys.modules[module_name]
        else:
            spec = importlib.util.spec_from_file_location(module_name, init_path)
            if spec is None or spec.loader is None:
                print(f"Warning: could not create import spec for pipeline '{pipeline_name}' at {init_path}")
                return
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (inspect.isclass(attr)
                    and issubclass(attr, Pipeline)
                    and attr is not Pipeline
                    and hasattr(attr, 'name')
                    and attr.name):
                _REGISTRY[attr.name] = attr
    except Exception as e:
        import traceback
        print(f"Warning: failed to load pipeline '{pipeline_name}' from {subdir}: {e}")
        traceback.print_exc()


def register_pipeline(name: str, cls):
    """Explicitly register a pipeline class by name."""
    _REGISTRY[name] = cls


def get_pipeline_class(name: str) -> type:
    """Get pipeline class by name. Discovers from filesystem if needed."""
    _discover_pipelines()
    if name not in _REGISTRY:
        raise KeyError(
            f"Pipeline '{name}' not found. Available: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[name]


def list_pipelines() -> list[str]:
    """List all registered pipeline names."""
    _discover_pipelines()
    # If discovery found nothing, allow retry on next call
    if not _REGISTRY:
        global _discovered
        _discovered = False
    return list(_REGISTRY.keys())


def create_pipelines(configs: list[dict]) -> PipelineStack:
    """
    Instantiate pipelines from a list of config dicts.
    Each dict must have a 'name' key matching a registered pipeline.

    Example configs:
        [
            {"name": "GridPilot", "gate": {"percentile": 80}},
            {"name": "MomentumPilot", "lookback": 20},
        ]
    """
    _discover_pipelines()
    pipelines = []
    for conf in configs:
        conf = dict(conf)
        name = conf.pop('name')
        cls = get_pipeline_class(name)
        pipelines.append(cls(conf))
    return PipelineStack(pipelines)
