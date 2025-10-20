# Local CI Dry-Run Requirements

To approximate the `CI` GitHub Actions workflow on a development workstation or in-container, install the same language runtimes,
Python packages, and supporting CLIs that the workflow provisions dynamically. The sections below list what already comes from
`requirements.txt` or `ci/bootstrap_tools.py` and which system packages must exist ahead of time so every job can run without
failing early.

## Python environment

The composite `setup-python-env` action pins Python 3.11 for every lane and installs:

- Core dependencies from [`requirements.txt`](../requirements.txt) – this brings in Ansible, ansible-lint, pre-commit, yamllint,
  check-jsonschema, and Sigstore tooling used across the lint and validation steps.
- Ansible collections declared in [`ci/collections-stable.yml`](../ci/collections-stable.yml) or
  [`ci/collections-latest.yml`](../ci/collections-latest.yml), depending on the matrix lane being exercised.

Create a virtual environment with Python 3.11 and install those requirements before invoking any of the workflow scripts locally.

## Verified CLI tooling

`ci/bootstrap_tools.py` downloads and verifies the remaining standalone binaries (actionlint, gitleaks, conftest, trivy, cosign,
and kind). Running the bootstrap script locally is sufficient as long as the build host has `curl`, `tar`, and `sha256sum`
available.

## Required system packages

Dry-running the workflow end-to-end also needs a handful of packages from the OS distribution:

- **Container runtime:** `docker.io`, `docker-buildx-plugin`, and `docker-compose-plugin` so `docker compose -f … config` and kind
  cluster creation succeed.
- **Kubernetes helpers:** `conntrack`, `iptables`, `iproute2`, `socat`, and `e2fsprogs` – these are prerequisites for running kind
  and for Kubernetes networking components used during the integration job.
- **Systemd utilities:** `systemd` (or `systemd-container`) to supply `systemd-analyze verify` for the Quadlet validation gate.
- **Privilege helpers:** `sudo` for stages that use privileged install paths when mirroring the GitHub-hosted runner behaviour.

Install those packages (or their equivalents on non-Debian distributions) inside the container before attempting a full dry run.
With the system dependencies and the Python environment in place, the CI workflow commands listed in
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) can be executed sequentially to match the hosted runner environment.
