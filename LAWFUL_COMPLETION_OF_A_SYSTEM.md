# Lawful Completion of a System

A system is not complete when it builds successfully.

A system is complete only when it has been verified, packaged into its declared distribution form, and proven to run correctly as a delivered artifact.

Completion requires:

- verified structure
- validated behavior
- generated distribution artifacts
- successful post-packaging execution

If any of these are missing, the system is not complete.

## Why It Matters

Build success proves only that source-level assembly succeeded under one development environment. It does not prove that the delivered system is present, runnable, intact, or truthful in its final form.

Lawful completion matters because the real point of a system is not source existence. The point is dependable delivery. A system can compile and still fail after packaging because:

- entry points are missing
- assets were not included
- runtime configuration was not carried forward
- packaging changed import resolution
- the shipped artifact cannot boot outside the repo

Without lawful completion, teams can falsely declare success while the actual delivered artifact is incomplete.

## Completion Test

A system reaches lawful completion only when all of the following are true:

1. Structure has been checked and required files are present.
2. Behavior has been verified against the intended runtime path.
3. The declared release form has been generated.
4. The packaged artifact has been executed successfully after packaging.

If the declared release form includes both an extracted folder and an archive, both must exist before completion can be claimed.

## ARIS Interpretation

Inside ARIS and Project Infi, lawful completion means delivery must remain governed by truth. The claim "complete" is lawful only when the system can prove:

- what was verified
- what was packaged
- what artifact was produced
- what post-package execution succeeded

This is why Shipping Lane exists as a separate authority from Build Lane. Build prepares output. Shipping proves delivered completion.
