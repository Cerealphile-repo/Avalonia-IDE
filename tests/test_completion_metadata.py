import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
CORE = ROOT / "core"


def _load_core_module(name):
    package = sys.modules.get("core")
    if package is None:
        package = types.ModuleType("core")
        package.__path__ = [str(CORE)]
        sys.modules["core"] = package

    fullname = f"core.{name}"
    module = sys.modules.get(fullname)
    if module is not None:
        return module

    spec = importlib.util.spec_from_file_location(fullname, CORE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    spec.loader.exec_module(module)
    return module


log = _load_core_module("log")
metadata = _load_core_module("completion_metadata")
_load_core_module("axaml")
_load_core_module("resource")
completion = _load_core_module("completion")


class CompletionMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = metadata.build_completion_metadata_index(ROOT / "metadata")
        cls.engine = completion.CompletionEngine(completion_metadata=cls.index)

    def test_metadata_shape(self):
        self.assertEqual(len(self.index.controls), 524)
        self.assertEqual(len(self.index.inheritance), 524)
        self.assertEqual(len(self.index.attached_properties), 51)
        self.assertEqual(
            sum(len(properties) for properties in self.index.attached_properties.values()),
            171,
        )

    def test_every_attached_owner_and_property_is_completable(self):
        for owner, properties in self.index.attached_properties.items():
            owners = self.engine.complete_attached_owners(owner)
            self.assertTrue(
                any(item.label.casefold() == owner.casefold() for item in owners),
                owner,
            )

            for name in properties:
                items = self.engine.complete_attached_properties(owner, name)
                self.assertTrue(
                    any(
                        item.label.casefold() == f"{owner}.{name}".casefold()
                        for item in items
                    ),
                    f"{owner}.{name}",
                )

    def test_every_control_with_properties_has_generic_property_completion(self):
        for control in self.index.controls:
            properties = self.index.get_properties(control)
            if not properties:
                continue

            first = properties[0]
            items = self.engine.complete_properties(control, first.name)
            self.assertTrue(
                any(item.label.casefold() == first.name.casefold() for item in items),
                f"{control}.{first.name}",
            )

    def test_values_are_reachable_through_property_metadata(self):
        checked = 0
        for control in self.index.controls:
            for prop in self.index.get_properties(control):
                if not prop.values:
                    continue
                items = self.engine.complete_property_values(control, prop.name)
                self.assertTrue(items, f"{control}.{prop.name}")
                checked += 1
                if checked >= 100:
                    return
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()
