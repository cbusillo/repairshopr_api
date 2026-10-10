# Security Policy

## Supported Versions

Only the latest release on PyPI is supported. Fixes ship in a new release
built from `main`.

## Reporting a Vulnerability

Report suspected vulnerabilities privately through GitHub's
[Report a vulnerability](https://github.com/cbusillo/repairshopr_api/security/advisories/new)
form. Do not open a public issue for a vulnerability.

Include the package version, the impact, and the smallest steps that
reproduce it.

Do not send API keys, customer records, ticket or invoice contents, or other
personal data. Use redacted or made-up values.

This is a single-maintainer project. Reports are handled on a best-effort
basis, and I aim to reply within seven days.

## Scope

Relevant reports include:

- API keys or database passwords showing up in logs, output, or saved
  settings;
- the sync service exposing customer data or writing it to the wrong
  database;
- unsafe handling of data the RepairShopr API sends back; and
- dependency, package publishing, or GitHub Actions supply-chain problems.

Problems in RepairShopr itself should go to RepairShopr.
