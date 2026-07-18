# SwanSong SDK 0.3.1 release notes

SwanSong SDK 0.3.1 is a focused Doctor interoperability hotfix. It does not
change the runtime or manifest schema.

## Reliable SwanSong diagnosis

`swan doctor` now completes its JSON-RPC initialize probe as soon as the
matching newline-delimited response arrives. MCP servers are designed to stay
alive for later requests, so Doctor no longer waits for server exit after a
successful handshake.

The probe still has a strict deadline, a 4 MiB response-line limit, exact
request-ID matching, JSON-RPC error handling, SwanSong server-name validation,
redacted command reporting, and process-group termination. Servers that remain
silent, return partial output, reject initialization, impersonate SwanSong, or
exit before replying continue to fail closed.

Game runtime behavior, generated project interfaces, cartridge ABI, manifest
schema 1, and play-evidence contracts are unchanged from 0.3.0.
