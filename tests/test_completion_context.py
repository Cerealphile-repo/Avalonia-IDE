import unittest

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "avalonia_completion_context",
    Path(__file__).parents[1] / "core" / "completion_context.py",
)
_completion_context = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _completion_context
_spec.loader.exec_module(_completion_context)
get_completion_context = _completion_context.get_completion_context


class CompletionContextTests(unittest.TestCase):
    def test_control_context_is_generic(self):
        for text, prefix in (("<", ""), ("<But", "But"), ("<local:My", "local:My")):
            context = get_completion_context(text)
            self.assertEqual(context.kind, "control")
            self.assertEqual(context.prefix, prefix)

    def test_normal_property_context(self):
        context = get_completion_context('<ControlA Content="Hello" Fo')
        self.assertEqual(context.kind, "property")
        self.assertEqual(context.control, "ControlA")
        self.assertEqual(context.prefix, "Fo")
        self.assertIn("content", context.existing_properties)

    def test_attached_property_context_is_not_grid_specific(self):
        for owner, prefix in (("OwnerA", "P"), ("OwnerB", "Q"), ("OwnerC", "R"), ("OwnerD", "S")):
            context = get_completion_context(f'<ControlA {owner}.{prefix}')
            self.assertEqual(context.kind, "attached_property")
            self.assertEqual(context.attached_owner, owner)
            self.assertEqual(context.attached_prefix, prefix)
            self.assertEqual(context.prefix, f"{owner}.{prefix}")

    def test_attached_property_value_context(self):
        context = get_completion_context('<ControlA OwnerA.Property="1" OwnerB.Value="')
        self.assertEqual(context.kind, "value")
        self.assertEqual(context.control, "ControlA")
        self.assertEqual(context.property, "OwnerB.Value")
        self.assertEqual(context.prefix, "")

    def test_quoted_angle_bracket_does_not_break_tag_context(self):
        context = get_completion_context('<ControlA Content="1 < 2" Fo')
        self.assertEqual(context.kind, "property")
        self.assertEqual(context.control, "ControlA")
        self.assertEqual(context.prefix, "Fo")

    def test_nested_tag_context(self):
        context = get_completion_context('<ControlRoot>\n  <ControlA Ca')
        self.assertEqual(context.kind, "property")
        self.assertEqual(context.control, "ControlA")
        self.assertEqual(context.prefix, "Ca")

    def test_resources_are_syntax_only(self):
        context = get_completion_context('{StaticResource My')
        self.assertEqual(context.kind, "resource")
        self.assertEqual(context.resource_kind, "StaticResource")
        self.assertEqual(context.prefix, "My")


if __name__ == "__main__":
    unittest.main()
