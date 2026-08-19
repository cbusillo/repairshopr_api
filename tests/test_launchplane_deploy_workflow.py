from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "launchplane-deploy.yml"
RECOVERY_REQUEST_WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "launchplane-recovery-request.yml"
)
RECOVERY_APPLY_REQUEST_WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "launchplane-recovery-apply-request.yml"
)
TESTS_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "tests.yml"
GITHUB_CONFIG_PATH = ROOT / ".github" / "github.json"
RETIRED_RECOVERY_WORKFLOW_PATH = (
    ROOT / ".github" / "workflows" / "launchplane-deploy-recovery-dry-run.yml"
)


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
        "deployment_record_id=result.deployment_record_id",
    )
    for fragment in repo_local_launchplane_fragments:
        assert fragment not in workflow_text


def test_launchplane_recovery_request_uses_authorized_workflow_run_bridge() -> None:
    deploy_workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    request_workflow_text = RECOVERY_REQUEST_WORKFLOW_PATH.read_text(encoding="utf-8")

    request_fragments = (
        "name: Launchplane Recovery Request",
        "workflow_dispatch:",
        "name: Stage bounded recovery request",
        "launchplane-recovery-request-${{ github.run_id }}",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "retention-days: 1",
    )
    for fragment in request_fragments:
        assert fragment in request_workflow_text

    deploy_fragments = (
        "github.event_name == 'workflow_run'",
        "github.event.workflow_run.name == 'Launchplane Recovery Request'",
        "github.event.workflow_run.event == 'workflow_dispatch'",
        "github.event.workflow_run.head_branch == 'main'",
        "github.event.workflow_run.head_repository.full_name == github.repository",
        "name: Inspect existing deploy reservation",
        "uses: cbusillo/launchplane/.github/workflows/"
        "reusable-generic-web-stable-deploy.yml@main",
        "artifact_id: staged-recovery-request",
        "source_git_ref: ${{ github.event.workflow_run.head_sha }}",
    )
    for fragment in deploy_fragments:
        assert fragment in deploy_workflow_text

    dry_run_deploy_workflow_text = deploy_workflow_text.split(
        "  recovery-apply:", maxsplit=1
    )[0]
    combined_workflow_text = request_workflow_text + dry_run_deploy_workflow_text
    assert "generic-web/deploy-recovery/apply" not in request_workflow_text
    assert "expected_recovery_digest" not in request_workflow_text
    assert "generic-web-deploy-recovery-dry-run@" not in combined_workflow_text
    assert "recovery_request_json:" not in deploy_workflow_text
    assert "id-token: write" not in request_workflow_text
    assert "  workflow_dispatch:" not in deploy_workflow_text
    assert not RETIRED_RECOVERY_WORKFLOW_PATH.exists()


def test_launchplane_recovery_apply_uses_digest_bound_workflow_run_bridge() -> None:
    deploy_workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    request_workflow_text = RECOVERY_APPLY_REQUEST_WORKFLOW_PATH.read_text(
        encoding="utf-8"
    )

    request_fragments = (
        "name: Launchplane Recovery Apply Request",
        "workflow_dispatch:",
        "expected_recovery_digest:",
        "name: Stage approved recovery apply request",
        "launchplane-recovery-apply-request-${{ github.run_id }}",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
        "retention-days: 1",
    )
    for fragment in request_fragments:
        assert fragment in request_workflow_text

    deploy_fragments = (
        "github.event.workflow_run.name == 'Launchplane Recovery Apply Request'",
        "github.event.workflow_run.event == 'workflow_dispatch'",
        "github.event.workflow_run.head_branch == 'main'",
        "github.event.workflow_run.head_repository.full_name == github.repository",
        "name: Apply approved deploy recovery",
        "launchplane-url: ${{ vars.LAUNCHPLANE_PUBLIC_URL }}",
        "expected-product: ${{ vars.LAUNCHPLANE_PRODUCT }}",
        "expected-instance: ${{ vars.LAUNCHPLANE_INSTANCE }}",
        "workflow-run-id: ${{ github.event.workflow_run.id }}",
        'timeout-ms: "120000"',
    )
    for fragment in deploy_fragments:
        assert fragment in deploy_workflow_text

    action_match = re.search(
        r"cbusillo/launchplane/\.github/actions/"
        r"generic-web-deploy-recovery-dry-run@(?P<sha>[0-9a-f]{40})",
        deploy_workflow_text,
    )
    assert action_match is not None
    assert action_match.group("sha") == "011988411ff063be8b1069b4588a4825fb4749a7"
    assert "id-token: write" not in request_workflow_text
    assert "launchplane-url" not in request_workflow_text
    recovery_apply_workflow_text = deploy_workflow_text.split(
        "  recovery-apply:", maxsplit=1
    )[1]
    for forbidden_fragment in (
        "actions/download-artifact@",
        "github-token:",
        "request-json:",
        "request<<EOF",
        "jq ",
        "route-path:",
        "payload-file:",
        "idempotency-key:",
        "expected-status:",
        "output-paths:",
        "response-output-file:",
        "retry-attempts:",
        "Verify adoption-only recovery result",
    ):
        assert forbidden_fragment not in recovery_apply_workflow_text
    assert recovery_apply_workflow_text.count("      - name:") == 1
    assert "  workflow_dispatch:" not in deploy_workflow_text


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
