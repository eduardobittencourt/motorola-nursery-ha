# SonarQube Cloud, CodeRabbit and coverage

Analysis settings are versioned alongside the code; credentials remain in
GitHub secrets. Keep the existing lint, tests and security checks enabled.

## SonarQube Cloud

The existing test workflow records branch coverage with relative source paths.
The Sonar job downloads coverage from the same run, combines it, exports
`coverage.xml` and invokes the scanner. The integration manifest supplies
`sonar.projectVersion`; never substitute a build number or commit SHA.
Intelbras and Motorola publish the current-HA suite; minimum-HA tests remain
mandatory compatibility checks. Tuya combines Python and synthetic-media suites.

Keep the new-code definition at **Previous version**, use the same Python
quality profile and **Sonar way** quality gate in all three HA repositories.
Keep existing global coverage floors; the gate focuses on changed code.
Vendored Tuya code is excluded from coverage/duplication metrics, not review.

Service setup, in this order:

1. Register `SONAR_TOKEN` with analysis access as both an Actions secret and a
   Dependabot secret. Do not put its value in files or PR discussions.
2. Disable Automatic Analysis under Sonar project Administration > Analysis
   Method before enabling CI analysis. These modes cannot run together.
3. Verify main and PR analysis, coverage import and project version. The first
   main analysis may have no computed gate until a baseline exists.
4. Require the app-owned `SonarCloud Code Analysis` check only after confirming
   it is reported for the relevant PRs; keep all existing required checks.

Fork PRs run the test suites without the scanner credential. Before enabling a
universal Sonar required check, establish a trusted maintainer-branch analysis
path for outside contributions; do not run untrusted PR code with secrets via
`pull_request_target`. Dependabot uses its own secret namespace.

## Validation

Run the repository's normal checks and inspect that coverage paths resolve to
`custom_components/motorola_nursery`. For Tuya, include the real synthetic-media suite and
package checks; coverage must include both test jobs. Validate analysis on
configuration PRs before changing merge rules. Keep the three repos aligned in
policy without replacing their own test matrices or protocol acceptance tests.

## CodeRabbit

`.coderabbit.yaml` enables automatic incremental reviews, including Dependabot
PRs, skips drafts and disables automatic review pauses after multiple commits. Use English for review feedback, public code comments and documentation. Review status blocks on unresolved findings; automatic approval
is limited to moderate merge risk. Path instructions focus on HA lifecycle,
protocol correctness, tests and workflow security. AGENTS.md owns integration
constraints. Keep the existing CodeRabbit required check and review protection.
Gitar is not used for these repositories.
