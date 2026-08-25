"""
Avalonia Workspace Parser

Parses Visual Studio solution (.sln) and MSBuild project (.csproj)
files into immutable metadata objects.

This module performs text/XML parsing only.

It never walks the filesystem, interacts with Sublime Text,
or indexes source files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional
import re
import xml.etree.ElementTree as ET


#
# ----------------------------------------------------------------------
# Project Metadata
# ----------------------------------------------------------------------
#


@dataclass(frozen=True)
class ProjectMetadata:
    """Metadata extracted from a .csproj file."""

    name: str

    project_file: Path

    sdk: Optional[str]

    framework: Optional[str]

    output_type: Optional[str]

    avalonia_version: Optional[str]

    executable: bool


#
# ----------------------------------------------------------------------
# Solution Metadata
# ----------------------------------------------------------------------
#


@dataclass(frozen=True)
class SolutionProject:
    """A project listed in a Visual Studio solution."""

    name: str

    project_file: Path


#
# ----------------------------------------------------------------------
# Solution Parser
# ----------------------------------------------------------------------
#

#
# Matches lines such as:
#
# Project("{GUID}") = "MyApp", "src\MyApp\MyApp.csproj", "{GUID}"
#

_PROJECT_PATTERN = re.compile(
    r'^Project\("\{[^"]+\}"\)\s*=\s*"([^"]+)",\s*"([^"]+)",'
)


def parse_solution(solution_file: Path) -> List[SolutionProject]:
    """
    Parse a Visual Studio .sln file.

    Returns every C# project contained in the solution.
    """

    solution_file = solution_file.resolve()

    projects: List[SolutionProject] = []

    root = solution_file.parent

    with solution_file.open(
        "r",
        encoding="utf-8",
        errors="ignore",
    ) as stream:

        for line in stream:

            match = _PROJECT_PATTERN.match(line)

            if not match:
                continue

            name, relative_path = match.groups()

            #
            # Ignore solution folders and non-MSBuild projects.
            #

            if not relative_path.lower().endswith(".csproj"):
                continue

            project_file = (root / relative_path).resolve()

            projects.append(
                SolutionProject(
                    name=name,
                    project_file=project_file,
                )
            )

    return projects


#
# ----------------------------------------------------------------------
# Project Parser
# ----------------------------------------------------------------------
#


def parse_project(project_file: Path) -> ProjectMetadata:
    """
    Parse a .csproj file into ProjectMetadata.
    """

    project_file = project_file.resolve()

    tree = ET.parse(project_file)

    root = tree.getroot()

    sdk = root.attrib.get("Sdk")

    framework = None
    output_type = None
    avalonia_version = None

    for group in root.findall("PropertyGroup"):

        value = group.findtext("TargetFramework")
        if value:
            framework = value

        value = group.findtext("OutputType")
        if value:
            output_type = value

    for group in root.findall("ItemGroup"):

        for package in group.findall("PackageReference"):

            include = package.attrib.get("Include", "")

            if include.startswith("Avalonia"):

                avalonia_version = package.attrib.get("Version")
                break

    return ProjectMetadata(
        name=project_file.stem,
        project_file=project_file,
        sdk=sdk,
        framework=framework,
        output_type=output_type,
        avalonia_version=avalonia_version,
        executable=(output_type or "").lower() == "exe",
    )
