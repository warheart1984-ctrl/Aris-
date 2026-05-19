# Signed Manifests

CoGOS signs curated local manifests before they are trusted by package and
update paths.

Signed files:

- `/opt/cogos/config/release_manifest.json`
- `/opt/cogos/config/package_catalog.json`
- `/opt/cogos/config/update_channel.json`

Each has a detached `.sig` file beside it. Verification uses canonical JSON
and the trust key registry at `/opt/cogos/config/trust_keys.json`.

## Commands

```sh
cogos-manifest verify-core
cogos-manifest verify /opt/cogos/config/package_catalog.json
cogos-pkg verify
cogos_update.py verify
```

The current ISO uses an offline HMAC-SHA256 root key for local tamper
detection. Replace the development key before public distribution or migrate
the verifier to an asymmetric key scheme.

