import tempfile
import unittest
from pathlib import Path

from core.csharp_semantic import build_csharp_index
from core.ide_features import (
    analyze_bindings,
    convert_attribute_to_property_element,
    extract_resource,
    extract_style,
    related_files,
    rename_resource_text,
    resource_scope_candidates,
    scaffold_view,
    scaffold_viewmodel, infer_namespace,
)
from core.resource import ResourceEntry, ResourceIndex


class IdeFeatureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'MainViewModel.cs').write_text('''namespace Demo;\npublic class MainViewModel { public Customer Customer { get; } public string Title { get; } }\npublic class Customer { public string Name { get; } public string City { get; } }\n''', encoding='utf8')
        self.index = build_csharp_index([self.root / 'MainViewModel.cs'])

    def tearDown(self):
        self.tmp.cleanup()

    def test_binding_typo_suggests_property(self):
        text = '<TextBlock Text="{Binding Custmer.Name}" />'
        issues = analyze_bindings(text, self.root / 'Main.axaml', 'MainViewModel', self.index)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].suggestion, 'Customer')

    def test_nested_binding_is_valid(self):
        text = '<TextBlock Text="{Binding Customer.City}" />'
        self.assertEqual(analyze_bindings(text, self.root / 'Main.axaml', 'MainViewModel', self.index), [])


    def test_binding_completion_after_trailing_dot(self):
        from core.binding import get_binding_context, complete_binding
        text = '<TextBlock Text="{Binding Customer.'
        context = get_binding_context(text, len(text), root_type='MainViewModel', index=self.index)
        self.assertIsNotNone(context)
        self.assertEqual(context.path, 'Customer.')
        self.assertEqual(context.prefix, '')
        self.assertEqual([p.name for p in complete_binding(context, self.index)], ['Name', 'City'])

    def test_resource_rename_is_scoped(self):
        text = '<Brush x:Key="PrimaryBrush" />\n<TextBlock Background="{DynamicResource PrimaryBrush}" />'
        changed, count = rename_resource_text(text, 'PrimaryBrush', 'AccentBrush')
        self.assertEqual(count, 2)
        self.assertIn('x:Key="AccentBrush"', changed)
        self.assertIn('{DynamicResource AccentBrush}', changed)

    def test_resource_scope_prefers_current_file(self):
        local = ResourceEntry('Brush', 'SolidColorBrush', self.root / 'Main.axaml')
        other = ResourceEntry('Brush', 'SolidColorBrush', self.root / 'App.axaml')
        idx = ResourceIndex({'Brush': (other, local)})
        result = resource_scope_candidates('Brush', self.root / 'Main.axaml', idx, '<Window.Resources>\n    <Brush x:Key="Brush" />\n</Window.Resources>', 35)
        self.assertEqual(result.entry, local)
        self.assertEqual(result.scope, 'current file (Window.Resources)')

    def test_resource_reference_regex_matches_static_and_dynamic(self):
        import re
        text = '<Border Background="{StaticResource TestBrush}"><TextBlock Foreground="{DynamicResource SecondaryBrush}" />'
        pattern = re.compile(r'''\{\s*(StaticResource|DynamicResource)\s+([^\s}"']+)\s*\}''', re.IGNORECASE)
        matches = list(pattern.finditer(text))
        self.assertEqual([(m.group(1), m.group(2)) for m in matches],
                         [('StaticResource', 'TestBrush'), ('DynamicResource', 'SecondaryBrush')])

    def test_extract_resource(self):
        source = '<Window>\n    <TextBlock Foreground="#ff0000" />\n</Window>'
        result = extract_resource(source, '#ff0000', 'DangerBrush')
        self.assertIn('x:Key="DangerBrush"', result)
        self.assertIn('{DynamicResource DangerBrush}', result)

    def test_extract_resource_targets_selected_duplicate(self):
        source = '<Window>\n    <TextBlock Foreground="#ff0000" />\n    <Border Background="#ff0000" />\n</Window>'
        offset = source.index('#ff0000', source.index('Background'))
        result = extract_resource(source, '#ff0000', 'DangerBrush', target_offset=offset)
        self.assertIn('Foreground="#ff0000"', result)
        self.assertIn('Background="{DynamicResource DangerBrush}"', result)

    def test_extract_resource_infers_string_for_non_color_literal(self):
        source = '<Window>\n    <TextBlock Text="Hello world" />\n</Window>'
        offset = source.index('Hello world')
        result = extract_resource(source, 'Hello world', 'GreetingText', target_offset=offset)
        self.assertIn('<x:String x:Key="GreetingText">Hello world</x:String>', result)
        self.assertIn('Text="{StaticResource GreetingText}"', result)

    def test_extract_resource_ignores_markup_extension(self):
        source = '<Window>\n    <TextBlock Text="{Binding Greeting}" />\n</Window>'
        offset = source.index('{Binding Greeting}')
        result = extract_resource(source, '{Binding Greeting}', 'GreetingText', target_offset=offset)
        self.assertEqual(result, source)

    def test_extract_resource_escapes_string_xml(self):
        source = '<Window>\n    <TextBlock Text="A &amp; B" />\n</Window>'
        offset = source.index('A &amp; B')
        result = extract_resource(source, 'A &amp; B', 'AmpText', target_offset=offset)
        self.assertIn('<x:String x:Key="AmpText">A &amp;amp; B</x:String>', result)

    def test_related_files_searches_project_root(self):
        views = self.root / 'Views'
        models = self.root / 'ViewModels'
        views.mkdir(); models.mkdir()
        axaml = views / 'CustomerView.axaml'
        axaml.write_text('<UserControl />', encoding='utf8')
        (models / 'CustomerViewModel.cs').write_text('', encoding='utf8')
        names = {p.name for p in related_files(axaml, self.root)}
        self.assertIn('CustomerViewModel.cs', names)

    def test_infer_namespace_from_root_namespace(self):
        csproj = self.root / 'Demo.csproj'
        csproj.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><RootNamespace>Company.Demo</RootNamespace></PropertyGroup></Project>', encoding='utf8')
        project = type('Project', (), {'project_file': csproj, 'root': self.root, 'name': 'Demo'})()
        self.assertEqual(infer_namespace(project), 'Company.Demo')

    def test_extract_style(self):
        source = '<Window><Button /></Window>'
        result = extract_style(source, 'Button', 'PrimaryButton', {'Padding': '10'})
        self.assertIn('<Style Selector="Button" x:Key="PrimaryButton">', result)
        self.assertIn('<Setter Property="Padding" Value="10" />', result)

    def test_extract_style_formats_resources_cleanly(self):
        source = '''<UserControl>
    <UserControl.Resources>
        <SolidColorBrush x:Key="TestBrush" />
    </UserControl.Resources>
</UserControl>'''
        result = extract_style(source, 'Button', 'TestButtonStyle', {'Grid.Row': '1', 'Content': 'Hello'})
        expected = '''    <UserControl.Resources>
        <SolidColorBrush x:Key="TestBrush" />
        <Style Selector="Button" x:Key="TestButtonStyle">
            <Setter Property="Grid.Row" Value="1" />
            <Setter Property="Content" Value="Hello" />
        </Style>
    </UserControl.Resources>'''
        self.assertIn(expected, result)

    def test_attribute_property_conversion(self):
        source = '<Button Content="Hello" Width="20" />'
        result = convert_attribute_to_property_element(source, 'Button', 'Content')
        self.assertIn('<Button Width="20">', result)
        self.assertIn('<Button.Content>Hello</Button.Content>', result)

    def test_attribute_property_conversion_preserves_indentation(self):
        source = """<StackPanel>
    <TextBlock
        Text=\"{Binding Greeting}\" />
</StackPanel>"""
        result = convert_attribute_to_property_element(source, 'TextBlock', 'Text')
        expected = """<StackPanel>
    <TextBlock>
        <TextBlock.Text>{Binding Greeting}</TextBlock.Text>
    </TextBlock>
</StackPanel>"""
        self.assertEqual(result, expected)

    def test_related_files(self):
        axaml = self.root / 'CustomerView.axaml'
        axaml.write_text('<UserControl />', encoding='utf8')
        for name in ('CustomerView.axaml.cs', 'CustomerViewModel.cs'):
            (self.root / name).write_text('', encoding='utf8')
        names = {p.name for p in related_files(axaml)}
        self.assertEqual(names, {'CustomerView.axaml.cs', 'CustomerViewModel.cs'})

    def test_scaffold_view(self):
        files = scaffold_view(self.root, 'SettingsView', 'Demo.Views')
        self.assertIn(self.root / 'SettingsView.axaml', files)
        self.assertIn('x:Class="Demo.Views.SettingsView"', files[self.root / 'SettingsView.axaml'])
        self.assertIn('InitializeComponent();', files[self.root / 'SettingsView.axaml.cs'])

    def test_scaffold_viewmodel(self):
        files = scaffold_viewmodel(self.root, 'SettingsViewModel', 'Demo.ViewModels')
        text = files[self.root / 'SettingsViewModel.cs']
        self.assertIn('INotifyPropertyChanged', text)
        self.assertIn('namespace Demo.ViewModels;', text)


if __name__ == '__main__':
    unittest.main()


    def test_extract_style_preserves_content_after_selected_control(self):
        source = '''<UserControl>\n    <StackPanel>\n        <Button Width="180" Height="42" Content="Extract" />\n        <TextBlock Text="Must remain" />\n    </StackPanel>\n</UserControl>'''
        selected = '<Button Width="180" Height="42" Content="Extract" />'
        replacement = '<Button Style="{StaticResource ExtractedButton}" />'
        # Model the command's intermediate text after resource insertion.
        intermediate = source.replace('<StackPanel>', '<StackPanel>\n    <UserControl.Resources>\n        <Style Selector="Button" x:Key="ExtractedButton">\n            <Setter Property="Width" Value="180" />\n        </Style>\n    </UserControl.Resources>')
        start = intermediate.find(selected)
        self.assertGreaterEqual(start, 0)
        result = intermediate[:start] + replacement + intermediate[start + len(selected):]
        self.assertIn(replacement, result)
        self.assertIn('<TextBlock Text="Must remain" />', result)
        self.assertTrue(result.endswith('</UserControl>'))
