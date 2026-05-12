# CoGOS v10 Release Notes

Release: `project-infi-aris-trixie-full-os-v10.iso`

SHA-256:

```text
48a3d6dbb87150cadc033cec9167e714afe802bc3cf86d5385033ce2f215c8a8
```

## Summary

CoGOS v10 is the Fast Operator Boot release for the Puppy/Trixie Hyper-V build.
It keeps the full v9 governance stack intact while making the default boot path
lighter, faster, and easier to operate.

## Highlights

- Fast operator boot with `operator_shell` as the default profile.
- Dashboard on-demand instead of autostart.
- Hyper-V helper defaults tuned to 4 CPUs and fixed 6GB startup memory.
- Governance stack unchanged from v9: law engine, sandboxed modules, Trait
  Identity Runtime, Pattern Ledger, immune recommendations, and proof flow all
  remain in place.

## Operator Commands

```sh
cogos-operator
cogos-perf
cogos-dashboard-start
cogos-dashboard-stop
cogos-desktop-hint
cogos-proof
```

## Verification Summary

- Payload verification passed.
- Python compile passed inside the Trixie rootfs.
- Boot smoke passed with `ok: true`.
- Dashboard was confirmed deferred by default.
- Dashboard start/stop wrappers passed.
- v9 proof sequence passed under the v10 payload.
- ISO mount sanity check passed.
- El Torito BIOS and UEFI boot entries are present.

