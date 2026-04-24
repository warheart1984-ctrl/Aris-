# release

This folder contains built and staged release artifacts for the nested
`code/code` project.

It is an artifact lane, not the primary source-authority lane.

## Owns

- packaged release outputs under platform-specific folders
- staged bundle, dist, build, and spec artifacts used during shipping
- variant packaging lanes such as current, operator-workspace, and
  project-picker builds

## Does Not Own

- source implementation in [`../evolving_ai/`](../evolving_ai/)
- live Forge/runtime code in [`../forge/`](../forge/)
- verification authority in [`../tests/`](../tests/)

## Main Folders

- [`windows/`](./windows/)
  - Windows-specific packaged outputs and spec/build folders

## Important Note

- Do not treat this folder as the place to make source edits. Update the source
  and shipping code first, then regenerate or verify the release artifacts.

## Read Next

1. [../README.md](../README.md)
2. [../LAWFUL_COMPLETION_OF_A_SYSTEM.md](../LAWFUL_COMPLETION_OF_A_SYSTEM.md)
3. [../evolving_ai/README.md](../evolving_ai/README.md)
4. [../tests/README.md](../tests/README.md)
