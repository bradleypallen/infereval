"""Context builders for :math:`\\mathrm{ctx}_\\Gamma` and :math:`\\mathrm{ctx}_\\Delta`.

A context builder is any callable ``(Sequence[str]) -> str`` that packages
a list of bearer expressions into a single natural-language context string.

Two flavors of builder are supported:

- **Template** (default): a format string with a ``{expressions}`` placeholder
  filled by joining bearer expressions with a configured ``joiner`` (e.g.
  ``" and "`` for premise contexts, ``" or "`` for conclusion contexts).
- **Plugin**: a dotted import path ``my_pkg.module:callable_name`` resolved
  at runtime, for analysts who need richer construction than a single joiner
  can express (e.g. topic-sensitive ordering).

Bearer expressions in benchmark JSON often contain TeX-math delimiters
(``$a$ is a stop sign``) so the LaTeX source compiles cleanly. We strip
those delimiters at prompt-construction time via :func:`strip_tex_math`
so the model sees plain prose (``a is a stop sign``).
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Sequence
from typing import Protocol

from .benchmark import (
    ContextBuilders,
    PluginContextBuilder,
    TemplateContextBuilder,
)

# ---- TeX stripping --------------------------------------------------------

_TEX_MATH_RE = re.compile(r"\$([^$]+)\$")


def strip_tex_math(text: str) -> str:
    """Strip ``$...$`` TeX-math delimiters, preserving their contents.

    Examples
    --------
    >>> strip_tex_math("$a$ is a stop sign")
    'a is a stop sign'
    >>> strip_tex_math("$a$ and $b$")
    'a and b'
    >>> strip_tex_math("no math here")
    'no math here'

    Unmatched single ``$`` characters are left in place; only paired
    ``$...$`` spans (without nested ``$``) are stripped.
    """
    return _TEX_MATH_RE.sub(r"\1", text)


# ---- ContextBuilder Protocol ---------------------------------------------


class ContextBuilder(Protocol):
    """Callable that turns a list of bearer expressions into a context string."""

    def __call__(self, expressions: Sequence[str]) -> str: ...


# ---- Template builder ----------------------------------------------------


def make_template_builder(
    *, template: str = "{expressions}", joiner: str = " and "
) -> ContextBuilder:
    """Build a context builder that joins expressions and formats into a template.

    Parameters
    ----------
    template
        Format string with a ``{expressions}`` placeholder.
    joiner
        Separator inserted between bearer expressions.

    Returns
    -------
    ContextBuilder
        Callable that takes a sequence of expressions and returns the
        formatted context.

    Notes
    -----
    The empty-input case returns the template formatted against an empty
    string, which by default yields the empty string. The endorser does not
    use this builder on empty implications (``I_M`` excludes ⟨∅, ∅⟩).
    """

    def _build(expressions: Sequence[str]) -> str:
        joined = joiner.join(expressions)
        return template.format(expressions=joined)

    return _build


# ---- Plugin builder ------------------------------------------------------


class PluginResolutionError(ValueError):
    """Raised when a plugin dotted path cannot be resolved to a callable."""


def resolve_plugin(dotted_path: str) -> ContextBuilder:
    """Resolve ``module.path:name`` to a callable context builder.

    The ``:`` separator distinguishes the module path from the attribute name
    so attribute-laden paths like ``my_pkg.builders.subpkg:CtxFactory().build``
    don't get misparsed. ``.`` is also accepted in place of ``:`` for
    simple cases like ``mypkg.module.fn``.
    """
    if ":" in dotted_path:
        module_path, _, attr = dotted_path.partition(":")
    elif "." in dotted_path:
        module_path, _, attr = dotted_path.rpartition(".")
    else:
        raise PluginResolutionError(
            f"Plugin path {dotted_path!r} is not a valid dotted path "
            "(expected 'module.path:callable' or 'module.path.callable')"
        )
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise PluginResolutionError(
            f"Could not import module {module_path!r} from plugin path {dotted_path!r}: {exc}"
        ) from exc
    try:
        obj = getattr(module, attr)
    except AttributeError as exc:
        raise PluginResolutionError(
            f"Module {module_path!r} has no attribute {attr!r} (from plugin path {dotted_path!r})"
        ) from exc
    if not callable(obj):
        raise PluginResolutionError(
            f"Plugin object at {dotted_path!r} is not callable"
        )
    return obj  # type: ignore[no-any-return]


# ---- Resolver: Pydantic config -> runtime callable ------------------------


def resolve_context_builder(
    model: TemplateContextBuilder | PluginContextBuilder,
) -> ContextBuilder:
    """Convert a benchmark's serialized context-builder config to a callable."""
    if isinstance(model, TemplateContextBuilder):
        return make_template_builder(template=model.template, joiner=model.joiner)
    if isinstance(model, PluginContextBuilder):
        return resolve_plugin(model.plugin)
    raise TypeError(f"Unsupported context-builder model: {type(model).__name__}")


def resolve_context_builders(
    builders: ContextBuilders,
) -> tuple[ContextBuilder, ContextBuilder]:
    """Resolve a :class:`ContextBuilders` pair into ``(premise, conclusion)`` callables."""
    return (
        resolve_context_builder(builders.premise),
        resolve_context_builder(builders.conclusion),
    )


__all__ = [
    "ContextBuilder",
    "PluginResolutionError",
    "make_template_builder",
    "resolve_context_builder",
    "resolve_context_builders",
    "resolve_plugin",
    "strip_tex_math",
]
