# Repository Rules

1. Use synthetic data only. Never add real PHI.
2. Do not implement image interpretation, diagnosis, clinical prioritization, or medical advice.
3. Do not implement DICOM deletion, pixel modification, tag-based identity modification, or automatic patient merging.
4. Keep AI output separate from action execution; AI text is untrusted data and never a command.
5. Validate every AI response with strict schemas that reject unexpected fields.
6. Apply deterministic policy checks after AI output and immediately before execution.
7. Require backend authentication and authorization for every protected route.
8. Audit every automated recommendation, validation, correction, approval, denial, override, execution, and outcome.
9. Never expose secrets to browser code, logs, fixtures, or Git.
10. Use RED–GREEN–REFACTOR for behavior changes and update relevant tests.
11. Use PostgreSQL transactions and row locks/version checks for booking.
12. Use idempotency keys and hard retry limits for external actions.
13. Keep Orthanc behind a typed, non-destructive adapter.
14. Keep AI providers behind a typed adapter with deterministic mock support.
15. Update architecture, API, data, safety, and phase documentation when interfaces change.
16. Run formatting, linting, type checks, tests, and real smoke checks before declaring a phase complete.
17. Do not weaken safety controls to make a demo pass.
18. Prefer safe failure and a human exception over unsupported automation.
19. Store no DICOM pixel data in PostgreSQL.
20. Include the synthetic-prototype disclaimer in the README and application footer.
