"""
Test Discovery - Discover and organize tests from YAML configurations.

Parses test suite YAML files, resolves test modules/functions, applies
tag- and platform-based filtering, and orders tests by dependency.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class TestSpec:
    """Specification of a single test case."""

    name: str
    module: str
    function: str
    tags: list[str] = field(default_factory=list)
    platform: list[str] = field(default_factory=list)
    timeout: float = 60.0
    requirements_ids: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    priority: int = 100  # lower = higher priority


# ---------------------------------------------------------------------------
# TestDiscovery
# ---------------------------------------------------------------------------

class TestDiscovery:
    """Discover tests from YAML suite definitions."""

    def discover(self, suite_path: Path) -> list[TestSpec]:
        """Load a YAML test-suite file and build a list of *TestSpec* objects."""
        if not suite_path.exists():
            logger.error("Suite file not found: %s", suite_path)
            return []

        with open(suite_path, "r", encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}

        suite_tags: list[str] = raw.get("tags", [])
        suite_platform: list[str] = raw.get("platform", [])
        tests: list[TestSpec] = []

        for entry in raw.get("tests", []):
            spec = TestSpec(
                name=entry["name"],
                module=entry["module"],
                function=entry.get("function", entry["name"]),
                tags=entry.get("tags", []) + suite_tags,
                platform=entry.get("platform", suite_platform),
                timeout=float(entry.get("timeout", 60)),
                requirements_ids=entry.get("requirements_ids", []),
                depends_on=entry.get("depends_on", []),
                priority=int(entry.get("priority", 100)),
            )
            tests.append(spec)

        logger.info("Discovered %d test(s) from %s", len(tests), suite_path.name)
        return tests

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    @staticmethod
    def filter_by_tags(tests: list[TestSpec], tags: list[str]) -> list[TestSpec]:
        """Return only tests whose tag list intersects *tags*."""
        tag_set = set(tags)
        return [t for t in tests if tag_set.intersection(t.tags)]

    @staticmethod
    def filter_by_platform(tests: list[TestSpec], platform: str) -> list[TestSpec]:
        """Return tests that support *platform* (or have no platform constraint)."""
        return [
            t for t in tests
            if not t.platform or platform in t.platform
        ]

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def _resolve_test_module(self, test_spec: TestSpec) -> Callable[..., Any] | None:
        """Import the test module and return the callable test function."""
        try:
            mod = importlib.import_module(test_spec.module)
            fn = getattr(mod, test_spec.function, None)
            if fn is None:
                logger.error(
                    "Function '%s' not found in module '%s'",
                    test_spec.function,
                    test_spec.module,
                )
            return fn
        except ModuleNotFoundError:
            logger.error("Module '%s' could not be imported", test_spec.module)
            return None
        except Exception:
            logger.exception("Unexpected error resolving %s.%s", test_spec.module, test_spec.function)
            return None

    # ------------------------------------------------------------------
    # Ordering
    # ------------------------------------------------------------------

    def _build_execution_order(self, tests: list[TestSpec]) -> list[TestSpec]:
        """Sort tests respecting *depends_on* relationships and priority.

        Uses a simple topological-ish sort: tests with unmet dependencies
        are placed after their dependencies; ties are broken by priority.
        """
        name_map: dict[str, TestSpec] = {t.name: t for t in tests}
        ordered: list[TestSpec] = []
        visited: set[str] = set()

        def _visit(spec: TestSpec) -> None:
            if spec.name in visited:
                return
            for dep_name in spec.depends_on:
                dep = name_map.get(dep_name)
                if dep and dep.name not in visited:
                    _visit(dep)
            visited.add(spec.name)
            ordered.append(spec)

        # Process in priority order so that equal-depth nodes are sorted
        for t in sorted(tests, key=lambda s: s.priority):
            _visit(t)

        return ordered
