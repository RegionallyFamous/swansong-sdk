# Release supply-chain records

Every successful `swan release` includes three deterministic, unsigned JSON
records in addition to `provenance.json` and `checksums.sha256`:

- `sbom.spdx.json` uses SPDX 2.3 and lists the packaged game artifacts,
  SwanSong SDK payload revision, and Wonderful toolchain lock.
- `sbom.cdx.json` uses CycloneDX 1.6 and records the same game, framework, and
  toolchain dependency graph.
- `attestation.intoto.json` is an in-toto Statement v1 with a SLSA provenance
  v1 predicate. Its subjects bind every pre-attestation release artifact.

The output is byte-stable for identical inputs. The fixed SPDX creation time is
a reproducibility sentinel, not a wall-clock build claim. The attestation is a
machine-readable build statement, not a signature: downstream release systems
may sign its exact bytes without changing SDK generation. Until then, its
integrity comes from its entry in `checksums.sha256` and the deterministic
release ZIP; it does not carry a Sigstore identity or independent verification
material.

Release fails closed before running or packaging when any of these are absent
or mutable:

- manifest `sdk.version` and content-addressed `sdk.revision`;
- the resolved SDK version and complete payload digest;
- the SHA-256 of `toolchain.lock`;
- the canonical sorted Wonderful package/version set for the active lane; or
- the digest-pinned Wonderful CI image.

The SBOM and attestation intentionally do not claim cartridge hardware QA,
legal authorization, or inspected gameplay. Those remain separate evidence
and release-policy gates.
