from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "launchplane-deploy.yml"
TESTS_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "tests.yml"
GITHUB_CONFIG_PATH = ROOT / ".github" / "github.json"


def test_launchplane_deploy_workflow_uses_reusable_generic_web_deploy() -> None:
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "name: Launchplane Deploy",
        "contents: read",
        "id-token: write",
        "packages: write",
        "uses: docker/login-action@v4",
        "uses: docker/build-push-action@v7",
        "file: docker/Dockerfile.sync",
        "artifact_id=",
        "uses: cbusillo/launchplane/.github/workflows/reusable-generic-web-stable-deploy.yml@main",
        "launchplane_url: ${{ vars.LAUNCHPLANE_PUBLIC_URL }}",
        "product: ${{ vars.LAUNCHPLANE_PRODUCT }}",
        "instance: ${{ vars.LAUNCHPLANE_INSTANCE }}",
        "artifact_id: ${{ needs.build-image.outputs.artifact_id }}",
        "source_git_ref: ${{ needs.build-image.outputs.source_git_ref }}",
    )
    for fragment in required_fragments:
        assert fragment in workflow_text

    repo_local_launchplane_fragments = (
        "cbusillo/launchplane/.github/actions/launchplane-request@main",
        "route-path: /v1/drivers/generic-web/deploy",
        "payload-file:",
        "idempotency-key:",
        "deployment_record_id=result.deployment_record_id",
    )
    for fragment in repo_local_launchplane_fragments:
        assert fragment not in workflow_text


def test_test_suite_uses_reusable_launchplane_config_authority_gate() -> None:
    workflow_text = TESTS_WORKFLOW_PATH.read_text(encoding="utf-8")
    github_config = json.loads(GITHUB_CONFIG_PATH.read_text(encoding="utf-8"))
    expected_workflow = github_config["qualityGate"]["configAuthority"]["workflow"]
    expected_revision = expected_workflow.rsplit("@", maxsplit=1)[1]
    revision_match = re.search(
        r"^\s+launchplane-revision:\s+(?P<revision>[0-9a-f]{40})$",
        workflow_text,
        re.MULTILINE,
    )

    assert re.fullmatch(
        r"cbusillo/launchplane/\.github/workflows/"
        r"reusable-product-repo-config-authority\.yml@[0-9a-f]{40}",
        expected_workflow,
    )
    assert f"uses: {expected_workflow}" in workflow_text
    assert revision_match is not None
    assert revision_match.group("revision") == expected_revision
    assert "reusable-product-repo-config-authority.yml@main" not in workflow_text

    repo_local_launchplane_fragments = (
        "repository: cbusillo/launchplane",
        "launchplaneRef",
        "audit-config-authority",
        "--control-plane-root",
        "--gate-profile product-repo",
    )
    for fragment in repo_local_launchplane_fragments:
        assert fragment not in workflow_text
