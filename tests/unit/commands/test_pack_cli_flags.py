"""Tests for new CLI flags in pack command (phase-3c, T-3c-01..12).

Covers:
- --marketplace filter validation (unknown format -> error)
- --marketplace-path FORMAT=PATH parsing + validation
- --json flag emits valid JSON on failure
"""

from __future__ import annotations

import json as _json
import textwrap as _tw
from pathlib import Path as _Path

import pytest
from click.testing import CliRunner

from apm_cli.commands.pack import pack_cmd


@pytest.fixture(autouse=True)
def _reset_console_state():
    """Reset console singleton; --json mode flips a global stream flag."""
    from apm_cli.utils.console import _reset_console

    yield
    _reset_console()


class TestMarketplaceFilterFlag:
    """T-3c-01..04: --marketplace flag parsing."""

    def test_unknown_format_raises(self) -> None:
        result = CliRunner().invoke(pack_cmd, ["--marketplace", "bogus"])
        assert result.exit_code != 0
        assert "Unknown marketplace format" in (
            result.output + (result.exception.__str__() if result.exception else "")
        )

    def test_unknown_format_json_mode(self) -> None:
        import json

        result = CliRunner().invoke(pack_cmd, ["--marketplace", "bogus", "--json"])
        # Should output valid JSON to stdout even on error
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert any("bogus" in e["message"] for e in data["errors"])


class TestMarketplacePathFlag:
    """T-3c-05..08: --marketplace-path parsing."""

    def test_missing_equals_raises(self) -> None:
        result = CliRunner().invoke(pack_cmd, ["--marketplace-path", "noequalssign"])
        assert result.exit_code != 0
        assert "FORMAT=PATH" in (
            result.output + (result.exception.__str__() if result.exception else "")
        )

    def test_unknown_format_raises(self) -> None:
        result = CliRunner().invoke(pack_cmd, ["--marketplace-path", "bogus=path.json"])
        assert result.exit_code != 0
        assert "Unknown marketplace format" in (
            result.output + (result.exception.__str__() if result.exception else "")
        )

    def test_missing_equals_json_mode(self) -> None:
        import json

        result = CliRunner().invoke(pack_cmd, ["--marketplace-path", "noequalssign", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["ok"] is False
        assert any("FORMAT=PATH" in e["message"] for e in data["errors"])


class TestJsonFlag:
    """T-3c-09..10: --json flag appears in help."""

    def test_json_in_help(self) -> None:
        result = CliRunner().invoke(pack_cmd, ["--help"])
        assert "--json" in result.output
        assert "machine-readable" in result.output.lower() or "JSON" in result.output


class TestMarketplaceOutputRemoved:
    """T-3c-11: --marketplace-output was removed in v0.16 (breaking change, #1318)."""

    def test_removed_flag_is_unknown_option(self) -> None:
        result = CliRunner().invoke(pack_cmd, ["--marketplace-output", "test.json"])
        assert result.exit_code != 0
        assert "no such option" in (result.output or "").lower() or isinstance(
            result.exception, SystemExit
        )


# ---------------------------------------------------------------------------
# Wave 4 release-gate flags: --check-versions / --check-clean
# ---------------------------------------------------------------------------


_APM_ALIGNED = """\
name: my-project
description: A project.
version: 1.0.0
marketplace:
  owner:
    name: ACME
  packages:
    - name: local-tool
      source: ./packages/local-tool
      description: Tool.
      version: 1.0.0
"""

_APM_ALIGNED_WITH_BUNDLE = _APM_ALIGNED + "dependencies: {}\n"

_APM_MISALIGNED = """\
name: my-project
description: A project.
version: 1.0.0
marketplace:
  owner:
    name: ACME
  packages:
    - name: local-tool
      source: ./packages/local-tool
      description: Tool.
      version: 0.9.0
"""


def _write_project(tmp_path: _Path, apm_yml: str, *, pkg_version: str = "1.0.0") -> _Path:
    (tmp_path / "apm.yml").write_text(_tw.dedent(apm_yml), encoding="utf-8")
    pkg_dir = tmp_path / "packages" / "local-tool"
    pkg_dir.mkdir(parents=True)
    pkg_dir.joinpath("apm.yml").write_text(
        f"name: local-tool\ndescription: Tool.\nversion: {pkg_version}\n",
        encoding="utf-8",
    )
    return tmp_path


_APM_PLUGIN_TARGET = """\
name: my-project
description: A project.
version: 1.0.9
license: MIT
targets: claude
"""

_GENERATED_PLUGIN_JSON = {
    "name": "my-project",
    "version": "1.0.9",
    "description": "A project.",
    "license": "MIT",
}


def _json_envelope(output: str) -> str:
    """Slice the ``--json`` envelope out of output that also carries log lines.

    ``CliRunner`` merges the logger's stderr into ``result.output``; the
    envelope is the pretty-printed object whose braces sit at column 0.
    """
    lines = output.splitlines()
    start = next(i for i, line in enumerate(lines) if line == "{")
    return "\n".join(lines[start:])


def _write_plugin_project(tmp_path: _Path, plugin_json: object) -> _Path:
    """A claude-target project, optionally carrying a committed plugin.json."""
    (tmp_path / "apm.yml").write_text(_APM_PLUGIN_TARGET, encoding="utf-8")
    skill = tmp_path / ".apm" / "skills" / "demo"
    skill.mkdir(parents=True, exist_ok=True)
    skill.joinpath("SKILL.md").write_text(
        "---\nname: demo\ndescription: A demo skill.\n---\n\nBody\n", encoding="utf-8"
    )
    if plugin_json is not None:
        target = tmp_path / ".claude-plugin" / "plugin.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        body = plugin_json if isinstance(plugin_json, str) else _json.dumps(plugin_json, indent=2)
        target.write_text(body + "\n", encoding="utf-8")
    return tmp_path


class TestHelpExitCodes:
    """Help text should document exit codes 3 and 4."""

    def test_exit_code_3_documented(self) -> None:
        result = CliRunner().invoke(pack_cmd, ["--help"])
        assert result.exit_code == 0
        assert "3" in result.output
        assert "--check-versions" in result.output

    def test_exit_code_4_documented(self) -> None:
        result = CliRunner().invoke(pack_cmd, ["--help"])
        assert result.exit_code == 0
        assert "4" in result.output
        assert "--check-clean" in result.output


class TestCheckVersionsFlag:
    """--check-versions release gate."""

    def test_flag_recognized(self) -> None:
        result = CliRunner().invoke(pack_cmd, ["--help"])
        assert "--check-versions" in result.output

    def test_skip_when_no_marketplace_block(self, tmp_path: _Path, monkeypatch) -> None:
        # apm.yml without a marketplace block -> skip gate, exit 0
        (tmp_path / "apm.yml").write_text(
            "name: x\ndescription: y\nversion: 1.0.0\n", encoding="utf-8"
        )
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(pack_cmd, ["--check-versions", "--dry-run"])
        # Build itself should succeed or fail with code 1 (not 3) since gate skipped.
        assert result.exit_code != 3

    def test_passes_with_aligned_versions(self, tmp_path: _Path, monkeypatch) -> None:
        _write_project(tmp_path, _APM_ALIGNED)
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(pack_cmd, ["--check-versions", "--dry-run", "--offline"])
        # Either gate passed (no exit 3) or bundle build hit unrelated failure;
        # the meaningful assertion is: exit code is not 3 (gate did not trip).
        assert result.exit_code != 3

    def test_fails_with_misaligned_versions(self, tmp_path: _Path, monkeypatch) -> None:
        _write_project(tmp_path, _APM_MISALIGNED, pkg_version="0.9.0")
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(pack_cmd, ["--check-versions", "--dry-run", "--offline"])
        assert result.exit_code == 3

    def test_json_envelope_carries_version_alignment(self, tmp_path: _Path, monkeypatch) -> None:
        _write_project(tmp_path, _APM_ALIGNED)
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(
            pack_cmd, ["--check-versions", "--dry-run", "--offline", "--json"]
        )
        data = _json.loads(result.output)
        assert "version_alignment" in data
        assert data["version_alignment"] is not None

    def test_json_envelope_drift_null_when_not_requested(
        self, tmp_path: _Path, monkeypatch
    ) -> None:
        _write_project(tmp_path, _APM_ALIGNED)
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(
            pack_cmd, ["--check-versions", "--dry-run", "--offline", "--json"]
        )
        data = _json.loads(result.output)
        assert "drift" in data
        assert data["drift"] is None


class TestCheckCleanFlag:
    """--check-clean release gate."""

    def test_flag_recognized(self) -> None:
        result = CliRunner().invoke(pack_cmd, ["--help"])
        assert "--check-clean" in result.output

    def test_skip_when_no_marketplace_block(self, tmp_path: _Path, monkeypatch) -> None:
        (tmp_path / "apm.yml").write_text(
            "name: x\ndescription: y\nversion: 1.0.0\ndependencies: {}\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(pack_cmd, ["--check-clean"])
        assert result.exit_code != 4
        assert "Marketplace drift check skipped" in result.output
        assert (
            "[dry-run] --check-clean is read-only; no pack outputs were written." in result.output
        )

    def test_fails_when_on_disk_missing(self, tmp_path: _Path, monkeypatch) -> None:
        _write_project(tmp_path, _APM_ALIGNED)
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(pack_cmd, ["--check-clean", "--dry-run", "--offline"])
        # No marketplace.json on disk -> "missing" -> exit 4.
        assert result.exit_code == 4

    def test_detects_drift_without_mutating_existing_output(
        self, tmp_path: _Path, monkeypatch
    ) -> None:
        _write_project(tmp_path, _APM_ALIGNED)
        monkeypatch.chdir(tmp_path)
        initial_pack = CliRunner().invoke(pack_cmd, ["--offline"])
        assert initial_pack.exit_code == 0, initial_pack.output
        output = tmp_path / ".claude-plugin" / "marketplace.json"
        initial_bytes = output.read_bytes()

        manifest = tmp_path / "apm.yml"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(
                "      version: 1.0.0", "      version: 1.0.1"
            ),
            encoding="utf-8",
        )

        result = CliRunner().invoke(pack_cmd, ["--check-clean", "--offline"])

        assert result.exit_code == 4, result.output
        assert output.read_bytes() == initial_bytes
        assert "[dry-run] Would write" not in result.output

    def test_reports_suppressed_bundle_output_as_read_only(
        self, tmp_path: _Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_project(tmp_path, _APM_ALIGNED_WITH_BUNDLE)
        monkeypatch.chdir(tmp_path)
        initial_pack = CliRunner().invoke(pack_cmd, ["--offline"])
        assert initial_pack.exit_code == 0, initial_pack.output

        result = CliRunner().invoke(pack_cmd, ["--check-clean", "--offline"])

        assert result.exit_code == 0, result.output
        assert (
            "[dry-run] --check-clean is read-only; no pack outputs were written." in result.output
        )
        assert "Packed" not in result.output

    def test_explicit_dry_run_keeps_full_bundle_and_marketplace_preview(
        self, tmp_path: _Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_project(tmp_path, _APM_ALIGNED_WITH_BUNDLE)
        monkeypatch.chdir(tmp_path)
        initial_pack = CliRunner().invoke(pack_cmd, ["--offline"])
        assert initial_pack.exit_code == 0, initial_pack.output

        result = CliRunner().invoke(
            pack_cmd,
            ["--check-clean", "--dry-run", "--offline"],
        )

        assert result.exit_code == 0, result.output
        assert "[dry-run] Would pack" in result.output
        assert "[dry-run] Would write marketplace.json" in result.output
        assert "[dry-run] --check-clean is read-only" not in result.output

    def test_json_envelope_carries_drift(self, tmp_path: _Path, monkeypatch) -> None:
        _write_project(tmp_path, _APM_ALIGNED)
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(pack_cmd, ["--check-clean", "--dry-run", "--offline", "--json"])
        data = _json.loads(result.output)
        assert "drift" in data
        assert data["drift"] is not None
        assert data["drift"]["ok"] is False

    def test_drift_error_includes_amend_recipe(self, tmp_path: _Path, monkeypatch) -> None:
        """Drift error output must include the commit --amend recovery recipe."""
        _write_project(tmp_path, _APM_ALIGNED)
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(pack_cmd, ["--check-clean", "--dry-run", "--offline"])
        assert result.exit_code == 4
        assert "commit --amend" in result.output

    def test_drift_error_includes_force_with_lease(self, tmp_path: _Path, monkeypatch) -> None:
        """Drift error output must include the force-with-lease recovery recipe."""
        _write_project(tmp_path, _APM_ALIGNED)
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(pack_cmd, ["--check-clean", "--dry-run", "--offline"])
        assert result.exit_code == 4
        assert "force-with-lease" in result.output

    def test_drift_error_includes_output_path(self, tmp_path: _Path, monkeypatch) -> None:
        """Drift error output must embed the affected path in the git add recipe line."""
        _write_project(tmp_path, _APM_ALIGNED)
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(pack_cmd, ["--check-clean", "--dry-run", "--offline"])
        assert result.exit_code == 4
        # Assert on a recipe-specific line that embeds the path; "marketplace.json"
        # alone was already present in the pre-recipe drift output (path display line).
        assert "git add" in result.output
        assert "marketplace.json" in result.output


class TestBothFlagsCombined:
    """Combined --check-versions + --check-clean: version exit (3) wins."""

    def test_both_flags_misaligned_versions_wins_exit_3(self, tmp_path: _Path, monkeypatch) -> None:
        _write_project(tmp_path, _APM_MISALIGNED, pkg_version="0.9.0")
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(
            pack_cmd, ["--check-versions", "--check-clean", "--dry-run", "--offline"]
        )
        # version-misalignment exit 3 takes precedence over drift exit 4
        assert result.exit_code == 3

    def test_both_flags_aligned_but_drift_exits_4(self, tmp_path: _Path, monkeypatch) -> None:
        _write_project(tmp_path, _APM_ALIGNED)
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(
            pack_cmd, ["--check-versions", "--check-clean", "--dry-run", "--offline"]
        )
        # versions pass; drift fails (no marketplace.json on disk) -> exit 4
        assert result.exit_code == 4

    def test_json_envelope_carries_both_payloads(self, tmp_path: _Path, monkeypatch) -> None:
        _write_project(tmp_path, _APM_ALIGNED)
        monkeypatch.chdir(tmp_path)
        result = CliRunner().invoke(
            pack_cmd,
            ["--check-versions", "--check-clean", "--dry-run", "--offline", "--json"],
        )
        data = _json.loads(result.output)
        assert data["version_alignment"] is not None
        assert data["drift"] is not None


class TestPluginManifestDriftGate:
    """--check-clean covers plugin.json, which pack never rewrites on its own.

    `apm pack` preserves an existing plugin.json unless --force is passed, so a
    manifest left behind by an earlier version keeps shipping its stale
    `version` to every consumer. Before #2553 no gate looked at the file:
    --check-versions only compared apm.yml against the marketplace strategy and
    --check-clean only diffed marketplace.json.
    """

    def test_stale_plugin_manifest_fails_the_gate(self, tmp_path: _Path, monkeypatch) -> None:
        """The exact #2553 repro: apm.yml moved to 1.0.9, plugin.json still says 1.0.8."""
        stale = dict(_GENERATED_PLUGIN_JSON, version="1.0.8")
        _write_plugin_project(tmp_path, stale)
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(pack_cmd, ["--check-clean"])

        assert result.exit_code == 4, result.output
        assert "Plugin manifest drift" in result.output
        assert "drift: version" in result.output

    def test_stale_plugin_manifest_is_not_rewritten_by_the_gate(
        self, tmp_path: _Path, monkeypatch
    ) -> None:
        """--check-clean stays read-only: it reports the drift, never repairs it."""
        stale = dict(_GENERATED_PLUGIN_JSON, version="1.0.8")
        _write_plugin_project(tmp_path, stale)
        monkeypatch.chdir(tmp_path)
        on_disk = tmp_path / ".claude-plugin" / "plugin.json"
        before = on_disk.read_bytes()

        CliRunner().invoke(pack_cmd, ["--check-clean"])

        assert on_disk.read_bytes() == before

    def test_matching_plugin_manifest_passes_quietly(self, tmp_path: _Path, monkeypatch) -> None:
        """A manifest that agrees with apm.yml is a no-op, not a warning."""
        _write_plugin_project(tmp_path, _GENERATED_PLUGIN_JSON)
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(pack_cmd, ["--check-clean"])

        assert result.exit_code == 0, result.output
        assert "Plugin manifest drift" not in result.output
        assert "already matches apm.yml" in result.output

    def test_hand_added_fields_are_not_drift(self, tmp_path: _Path, monkeypatch) -> None:
        """Keys APM does not generate belong to the author and are left alone.

        The never-overwrite policy exists so hand-maintained manifests survive;
        a gate that failed on extra keys would defeat it.
        """
        extended = dict(_GENERATED_PLUGIN_JSON, author={"name": "Someone"}, x_custom=[1, 2])
        _write_plugin_project(tmp_path, extended)
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(pack_cmd, ["--check-clean"])

        assert result.exit_code == 0, result.output
        assert "Plugin manifest drift" not in result.output

    def test_absent_plugin_manifest_is_not_drift(self, tmp_path: _Path, monkeypatch) -> None:
        """Nothing committed means nothing stale ships; pack would create it."""
        _write_plugin_project(tmp_path, None)
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(pack_cmd, ["--check-clean"])

        assert result.exit_code == 0, result.output
        assert "Plugin manifest drift" not in result.output

    def test_unreadable_plugin_manifest_fails_the_gate(self, tmp_path: _Path, monkeypatch) -> None:
        """A manifest that is not JSON cannot be the one apm.yml describes."""
        _write_plugin_project(tmp_path, "{ not json")
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(pack_cmd, ["--check-clean"])

        assert result.exit_code == 4, result.output
        assert "not a JSON object" in result.output

    def test_json_envelope_names_the_stale_manifest(self, tmp_path: _Path, monkeypatch) -> None:
        """CI consumers get the drifting fields without scraping stderr."""
        stale = dict(_GENERATED_PLUGIN_JSON, version="1.0.8", description="Old.")
        _write_plugin_project(tmp_path, stale)
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(pack_cmd, ["--check-clean", "--json"])

        data = _json.loads(_json_envelope(result.output))
        assert result.exit_code == 4
        assert data["ok"] is False
        entries = data["plugin_manifests"]["stale"]
        assert len(entries) == 1
        assert entries[0]["path"].endswith("plugin.json")
        assert sorted(entries[0]["fields"]) == ["description", "version"]
        # A stale manifest is still a preserved one: the pre-existing
        # ``skipped`` list keeps reporting it for existing consumers.
        assert data["plugin_manifests"]["skipped"] == [entries[0]["path"]]
        assert any(e["code"] == "plugin_manifest_drift" for e in data["errors"])

    def test_stale_manifest_alone_does_not_fail_a_plain_pack(
        self, tmp_path: _Path, monkeypatch
    ) -> None:
        """Without the gate, drift is a loud warning -- pack still never clobbers."""
        stale = dict(_GENERATED_PLUGIN_JSON, version="1.0.8")
        _write_plugin_project(tmp_path, stale)
        monkeypatch.chdir(tmp_path)

        result = CliRunner().invoke(pack_cmd, [])

        assert result.exit_code == 0, result.output
        assert "disagrees with apm.yml on: version" in result.output
