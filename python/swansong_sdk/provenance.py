"""Deterministic software-bill-of-materials and build-attestation records."""

from __future__ import annotations

import hashlib
import re
from typing import Mapping
import uuid

from .manifest import Manifest


SPDX_SCHEMA = "SPDX-2.3"
CYCLONEDX_SCHEMA = "1.6"
ATTESTATION_PREDICATE = "https://slsa.dev/provenance/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SDK_REVISION = re.compile(r"^sha256:[0-9a-f]{64}$")
_PINNED_IMAGE = re.compile(r"^.+@sha256:[0-9a-f]{64}$")


class ProvenanceError(ValueError):
    """A release dependency identity is absent, mutable, or inconsistent."""


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha1(payload: bytes) -> str:
    return hashlib.sha1(payload).hexdigest()


def validate_provenance(
    value: object, *, sdk_version: str, sdk_revision: str, lock_sha256: str,
    lock_payload: bytes | None = None,
) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("schema") != "swansong-build-provenance-v1":
        raise ProvenanceError("release provenance has an unsupported schema")
    if value.get("sdkVersion") != sdk_version or value.get("sdkRevision") != sdk_revision:
        raise ProvenanceError("release provenance SDK identity is not the resolved payload")
    if not _SDK_REVISION.fullmatch(sdk_revision):
        raise ProvenanceError("release provenance SDK revision is not content-addressed")
    toolchain = value.get("toolchain")
    if not isinstance(toolchain, dict):
        raise ProvenanceError("release provenance has no Wonderful toolchain identity")
    if toolchain.get("lockSha256") != lock_sha256 or not _SHA256.fullmatch(lock_sha256):
        raise ProvenanceError("release provenance does not match toolchain.lock")
    if toolchain.get("lane") not in {"native", "ci", "test"}:
        raise ProvenanceError("release provenance has an unknown toolchain lane")
    packages = toolchain.get("expectedPackages")
    if (not isinstance(packages, list) or not packages or
            not all(isinstance(item, str) and item.strip() for item in packages)):
        raise ProvenanceError("release provenance has no pinned Wonderful packages")
    if packages != sorted(packages) or len(packages) != len(set(packages)):
        raise ProvenanceError("release provenance Wonderful packages are not canonical")
    image = toolchain.get("canonicalImage")
    if not isinstance(image, str) or not _PINNED_IMAGE.fullmatch(image):
        raise ProvenanceError("release provenance has no digest-pinned Wonderful image")
    lane = toolchain["lane"]
    if lane != "test":
        if lock_payload is None or sha256(lock_payload) != lock_sha256:
            raise ProvenanceError("release validation has no matching toolchain lock payload")
        locked_packages, locked_image = _locked_toolchain(lock_payload, str(lane))
        if packages != locked_packages:
            raise ProvenanceError("release provenance Wonderful packages differ from toolchain.lock")
        if image != locked_image:
            raise ProvenanceError("release provenance Wonderful image differs from toolchain.lock")
    return value


def _locked_toolchain(payload: bytes, lane: str) -> tuple[list[str], str]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ProvenanceError("toolchain.lock is not UTF-8") from exc
    native: dict[str, str] = {}
    overrides: dict[str, str] = {}
    image: str | None = None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if _PINNED_IMAGE.fullmatch(line):
            image = line
            continue
        destination = native
        if line.startswith("ci:"):
            destination = overrides
            line = line.removeprefix("ci:").strip()
        pieces = line.split(maxsplit=1)
        if len(pieces) != 2:
            raise ProvenanceError(f"invalid toolchain.lock entry: {raw}")
        destination[pieces[0]] = pieces[1]
    if image is None:
        raise ProvenanceError("toolchain.lock has no digest-pinned Wonderful image")
    selected = dict(native)
    if lane == "ci":
        selected.update(overrides)
    return [f"{name} {version}" for name, version in sorted(selected.items())], image


def _file_id(path: str) -> str:
    return "SPDXRef-File-" + hashlib.sha256(path.encode()).hexdigest()[:16]


def _document_seed(manifest: Manifest, provenance: Mapping[str, object],
                   artifacts: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for value in (manifest.id, manifest.version, str(provenance["sdkRevision"])):
        digest.update(value.encode())
        digest.update(b"\0")
    for path, payload in sorted(artifacts.items()):
        digest.update(path.encode())
        digest.update(bytes.fromhex(sha256(payload)))
    return digest.hexdigest()


def spdx_sbom(manifest: Manifest, provenance: Mapping[str, object],
              artifacts: Mapping[str, bytes]) -> dict[str, object]:
    seed = _document_seed(manifest, provenance, artifacts)
    game_id = "SPDXRef-Package-Game"
    sdk_id = "SPDXRef-Package-SwanSong-SDK"
    wonderful_id = "SPDXRef-Package-Wonderful"
    toolchain = provenance["toolchain"]
    assert isinstance(toolchain, Mapping)
    files = [{
        "SPDXID": _file_id(path),
        "checksums": [
            {"algorithm": "SHA1", "checksumValue": sha1(payload)},
            {"algorithm": "SHA256", "checksumValue": sha256(payload)},
        ],
        "fileName": f"./{path}",
    } for path, payload in sorted(artifacts.items())]
    verification_code = hashlib.sha1("".join(sorted(
        sha1(payload) for payload in artifacts.values()
    )).encode("ascii")).hexdigest()
    relationships = [
        {"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES",
         "relatedSpdxElement": game_id},
        {"spdxElementId": game_id, "relationshipType": "DEPENDS_ON",
         "relatedSpdxElement": sdk_id},
        {"spdxElementId": wonderful_id, "relationshipType": "BUILD_TOOL_OF",
         "relatedSpdxElement": game_id},
    ]
    relationships.extend({
        "spdxElementId": game_id,
        "relationshipType": "CONTAINS",
        "relatedSpdxElement": item["SPDXID"],
    } for item in files)
    return {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {
            "created": "1970-01-01T00:00:00Z",
            "creators": [f"Tool: SwanSong SDK-{provenance['sdkVersion']}"],
        },
        "dataLicense": "CC0-1.0",
        "documentNamespace": f"urn:swansong:spdx:{manifest.id}:{manifest.version}:{seed}",
        "files": files,
        "name": f"{manifest.title} {manifest.version}",
        "packages": [
            {
                "SPDXID": game_id, "downloadLocation": "NOASSERTION",
                "filesAnalyzed": True, "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION", "name": manifest.title,
                "packageVerificationCode": {
                    "packageVerificationCodeValue": verification_code,
                },
                "versionInfo": manifest.version,
            },
            {
                "SPDXID": sdk_id, "downloadLocation": "NOASSERTION",
                "externalRefs": [{
                    "referenceCategory": "OTHER",
                    "referenceLocator": str(provenance["sdkRevision"]),
                    "referenceType": "swansong-payload-sha256",
                }],
                "filesAnalyzed": False, "licenseConcluded": "MIT",
                "licenseDeclared": "MIT", "name": "SwanSong SDK",
                "versionInfo": str(provenance["sdkVersion"]),
            },
            {
                "SPDXID": wonderful_id, "downloadLocation": str(toolchain["canonicalImage"]),
                "externalRefs": [{
                    "referenceCategory": "OTHER",
                    "referenceLocator": str(toolchain["lockSha256"]),
                    "referenceType": "swansong-toolchain-lock-sha256",
                }],
                "filesAnalyzed": False, "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION", "name": "Wonderful Toolchain",
                "versionInfo": str(toolchain["lane"]),
            },
        ],
        "relationships": relationships,
        "spdxVersion": SPDX_SCHEMA,
    }


def cyclonedx_sbom(manifest: Manifest, provenance: Mapping[str, object],
                   artifacts: Mapping[str, bytes]) -> dict[str, object]:
    seed = _document_seed(manifest, provenance, artifacts)
    serial = uuid.uuid5(uuid.NAMESPACE_URL, f"urn:swansong:cyclonedx:{seed}")
    toolchain = provenance["toolchain"]
    assert isinstance(toolchain, Mapping)
    game_ref = f"pkg:generic/{manifest.id}@{manifest.version}"
    sdk_ref = f"pkg:generic/swansong-sdk@{provenance['sdkVersion']}"
    wonderful_ref = "pkg:generic/wonderful-toolchain@" + str(toolchain["lane"])
    return {
        "bomFormat": "CycloneDX",
        "components": [
            {
                "bom-ref": sdk_ref,
                "hashes": [{"alg": "SHA-256", "content": str(provenance["sdkRevision"])[7:]}],
                "licenses": [{"license": {"id": "MIT"}}],
                "name": "SwanSong SDK", "type": "framework",
                "version": str(provenance["sdkVersion"]),
            },
            {
                "bom-ref": wonderful_ref,
                "hashes": [{"alg": "SHA-256", "content": str(toolchain["lockSha256"])}],
                "name": "Wonderful Toolchain",
                "properties": [
                    {"name": "swansong:canonical-image", "value": str(toolchain["canonicalImage"])},
                    {"name": "swansong:packages", "value": "\n".join(toolchain["expectedPackages"])},
                ],
                "type": "application", "version": str(toolchain["lane"]),
            },
        ],
        "dependencies": [{"ref": game_ref, "dependsOn": [sdk_ref, wonderful_ref]}],
        "metadata": {
            "component": {
                "bom-ref": game_ref,
                "hashes": [{"alg": "SHA-256", "content": seed}],
                "name": manifest.title, "type": "application",
                "version": manifest.version,
            },
            "tools": {"components": [{
                "name": "SwanSong SDK", "type": "application",
                "version": str(provenance["sdkVersion"]),
            }]},
        },
        "serialNumber": f"urn:uuid:{serial}",
        "specVersion": CYCLONEDX_SCHEMA,
        "version": 1,
    }


def build_attestation(manifest: Manifest, provenance: Mapping[str, object],
                      artifacts: Mapping[str, bytes]) -> dict[str, object]:
    seed = _document_seed(manifest, provenance, artifacts)
    toolchain = provenance["toolchain"]
    assert isinstance(toolchain, Mapping)
    manifest_payload = (manifest.root / "swan.toml").read_bytes()
    return {
        "_type": "https://in-toto.io/Statement/v1",
        "predicate": {
            "buildDefinition": {
                "buildType": "https://regionallyfamous.dev/swansong/build/v1",
                "externalParameters": {
                    "game": manifest.id,
                    "manifestSHA256": sha256(manifest_payload),
                    "version": manifest.version,
                },
                "internalParameters": {"deterministic": True},
                "resolvedDependencies": [
                    {"digest": {"sha256": str(provenance["sdkRevision"])[7:]},
                     "uri": f"pkg:generic/swansong-sdk@{provenance['sdkVersion']}"},
                    {"digest": {"sha256": str(toolchain["lockSha256"])},
                     "uri": str(toolchain["canonicalImage"])},
                ],
            },
            "runDetails": {
                "builder": {"id": f"https://regionallyfamous.dev/swansong-sdk/{provenance['sdkVersion']}"},
                "byproducts": [{"name": "swansong-build-provenance-v1", "value": dict(provenance)}],
                "metadata": {"invocationId": f"urn:sha256:{seed}"},
            },
        },
        "predicateType": ATTESTATION_PREDICATE,
        "subject": [{
            "digest": {"sha256": sha256(payload)}, "name": path,
        } for path, payload in sorted(artifacts.items())],
    }


def supply_chain_artifacts(manifest: Manifest, provenance: Mapping[str, object],
                           artifacts: Mapping[str, bytes]) -> dict[str, dict[str, object]]:
    return {
        "attestation.intoto.json": build_attestation(manifest, provenance, artifacts),
        "sbom.cdx.json": cyclonedx_sbom(manifest, provenance, artifacts),
        "sbom.spdx.json": spdx_sbom(manifest, provenance, artifacts),
    }
