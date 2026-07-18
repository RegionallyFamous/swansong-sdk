from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from swansong_sdk.identity import sdk_identity
from swansong_sdk.layout import sdk_root
from swansong_sdk.manifest import load_manifest
from swansong_sdk.provenance import (
    ProvenanceError, supply_chain_artifacts, validate_provenance,
)
from swansong_sdk.scaffold import create_project


class ProvenanceTests(unittest.TestCase):
    def fixture(self, root: Path):
        project = create_project("supply-game", "menu-puzzle", root / "game")
        manifest = load_manifest(project / "swan.toml")
        identity = sdk_identity()
        lock_sha = hashlib.sha256((sdk_root() / "toolchain.lock").read_bytes()).hexdigest()
        provenance = {
            "schema": "swansong-build-provenance-v1",
            "sdkVersion": identity["version"],
            "sdkRevision": identity["revision"],
            "toolchain": {
                "canonicalImage": "example.invalid/wonderful@sha256:" + "1" * 64,
                "expectedPackages": ["target-wswan 1", "wf-tools 2"],
                "lane": "test",
                "lockSha256": lock_sha,
            },
        }
        return manifest, identity, lock_sha, provenance

    def test_supply_chain_documents_are_deterministic_and_hash_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest, identity, lock_sha, provenance = self.fixture(Path(temporary))
            validate_provenance(
                provenance, sdk_version=identity["version"],
                sdk_revision=identity["revision"], lock_sha256=lock_sha,
            )
            artifacts = {"report.json": b"{}\n", "rom/supply_game.wsc": b"ROM"}
            first = supply_chain_artifacts(manifest, provenance, artifacts)
            second = supply_chain_artifacts(manifest, provenance, artifacts)
            self.assertEqual(first, second)
            self.assertEqual(sorted(first), [
                "attestation.intoto.json", "sbom.cdx.json", "sbom.spdx.json",
            ])
            self.assertEqual(first["sbom.spdx.json"]["spdxVersion"], "SPDX-2.3")
            game_package = first["sbom.spdx.json"]["packages"][0]
            file_sha1s = sorted(
                next(check["checksumValue"] for check in item["checksums"]
                     if check["algorithm"] == "SHA1")
                for item in first["sbom.spdx.json"]["files"]
            )
            expected_code = hashlib.sha1("".join(file_sha1s).encode("ascii")).hexdigest()
            self.assertEqual(
                game_package["packageVerificationCode"]["packageVerificationCodeValue"],
                expected_code,
            )
            self.assertEqual(first["sbom.cdx.json"]["bomFormat"], "CycloneDX")
            subjects = first["attestation.intoto.json"]["subject"]
            self.assertEqual([item["name"] for item in subjects], sorted(artifacts))
            for value in first.values():
                json.dumps(value, sort_keys=True)

    def test_provenance_rejects_mutable_or_incomplete_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, identity, lock_sha, provenance = self.fixture(Path(temporary))
            broken = dict(provenance)
            broken["toolchain"] = dict(provenance["toolchain"], canonicalImage="latest")
            with self.assertRaisesRegex(ProvenanceError, "digest-pinned"):
                validate_provenance(
                    broken, sdk_version=identity["version"],
                    sdk_revision=identity["revision"], lock_sha256=lock_sha,
                )
            broken["toolchain"] = dict(provenance["toolchain"], expectedPackages=[])
            with self.assertRaisesRegex(ProvenanceError, "no pinned"):
                validate_provenance(
                    broken, sdk_version=identity["version"],
                    sdk_revision=identity["revision"], lock_sha256=lock_sha,
                )

    def test_native_provenance_must_exactly_match_lock_contents(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            _, identity, lock_sha, provenance = self.fixture(Path(temporary))
            lock_payload = (sdk_root() / "toolchain.lock").read_bytes()
            packages: dict[str, str] = {}
            image = ""
            for raw in lock_payload.decode().splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or line.startswith("ci:"):
                    continue
                if "@sha256:" in line:
                    image = line
                    continue
                name, version = line.split(maxsplit=1)
                packages[name] = version
            provenance["toolchain"] = {
                "canonicalImage": image,
                "expectedPackages": [
                    f"{name} {version}" for name, version in sorted(packages.items())
                ],
                "lane": "native",
                "lockSha256": lock_sha,
            }
            validate_provenance(
                provenance, sdk_version=identity["version"],
                sdk_revision=identity["revision"], lock_sha256=lock_sha,
                lock_payload=lock_payload,
            )
            provenance["toolchain"]["expectedPackages"] = ["target-wswan latest"]
            with self.assertRaisesRegex(ProvenanceError, "differ from"):
                validate_provenance(
                    provenance, sdk_version=identity["version"],
                    sdk_revision=identity["revision"], lock_sha256=lock_sha,
                    lock_payload=lock_payload,
                )


if __name__ == "__main__":
    unittest.main()
