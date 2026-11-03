# CI and analysis

[Documentation index](../README.md)

`.github/workflows/validate.yml` defines HACS, hassfest and the minimum/current
HA test matrix, including hash-locked dependency installation, Ruff, Bandit and
coverage. Use the workflow and requirements files for exact pins and check names.
CodeQL analyzes Python and Actions in its own workflow.

Sonar imports current-HA coverage from the same workflow run and reads the
project version from the integration manifest.
Minimum-HA tests remain mandatory compatibility checks. Analysis settings live
in `sonar-project.properties`; review settings live in `.coderabbit.yaml`.
Credentials belong in GitHub secrets and must not be exposed to untrusted PR
code. Fork PRs need a safe test path without scanner credentials.

Dependabot updates are reviewed and merged manually; no workflow enables
dependency auto-merge. These merges do not publish releases. Repository settings
are authoritative for required reviews, branch freshness and merge protection.
Resolve conflicts, failing checks and review findings before merge.

Keep analyzer findings reviewable without weakening assertions or excluding
runtime modules to improve metrics. HA callbacks must preserve their awaitable
framework contract. Protocol constants and legacy formats need contextual
review; see [security](../reference/security.md). Synthetic tests must not depend
on real accounts, email delivery, camera credentials or private captures.

Use [testing](testing.md) to reproduce checks and maintain dependency locks.
Changes to minimum HA support must keep `hacs.json`, README and matrix aligned.

The required Sonar status check is `SonarQube scan`, provided by GitHub Actions
(app ID `15368`). The scanner runs with `sonar.qualitygate.wait=true`, so this
job fails if analysis fails or the quality gate is rejected. Keep the required
check name aligned with the workflow job; the separate SonarCloud GitHub App
check, `SonarCloud Code Analysis`, is not required by this CI setup. Fork PRs
run the test jobs while `SonarQube scan` and its quality gate are skipped;
scanner credentials are never provided to fork PRs.

## SonarQube Cloud setup

Use CI-based analysis with coverage and leave automatic analysis disabled.
The built-in **Sonar way** quality gate and the `previous_version` new-code
period are configured in SonarQube Cloud. CI supplies the integration manifest
version, a full Git history and coverage from the same workflow run. The
scanner's `sonar.qualitygate.wait=true` makes rejected gates fail the job.

Keep the SonarQube Cloud project bound to the correct GitHub repository and
allow the SonarQube Cloud GitHub App to access it. The native app publishes
`SonarCloud Code Analysis` and PR summaries separately from the Actions job.
Validate that check on a real PR before adding it to required status checks;
a successful scanner job alone does not prove that GitHub decoration works.

Fork PRs run tests without the Sonar token. Before merging an external
contribution that needs analysis, review it and bring the change to a branch
in this repository so the ordinary CI scanner can analyze it with coverage.
A skipped fork scan must not be treated as a successful Sonar analysis. No
privileged fork-analysis workflow is configured.

PNG files in the integration's brand directory are excluded from textual
analysis to prevent UTF-8 warnings on binary images. Runtime source and
workflow files remain in scope; existing coverage and license boundaries are
unchanged.

References:

- [SonarQube Cloud with GitHub Actions](https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/ci-based-analysis/github-actions-for-sonarcloud)
- [GitHub project integration](https://docs.sonarsource.com/sonarqube-cloud/managing-your-projects/administering-your-projects/devops-platform-integration/github)
