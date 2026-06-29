from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "launchplane-deploy.yml"


def test_launchplane_deploy_workflow_uses_launchplane_image_deploy_route() -> None:
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "name: Launchplane Deploy",
        "contents: read",
        "id-token: write",
        "packages: write",
        "uses: docker/login-action@v4",
        "uses: docker/build-push-action@v7",
        "file: docker/Dockerfile.sync",
        "artifact_id: $artifactId",
        "product: $product",
        "cbusillo/launchplane/.github/actions/launchplane-request@main",
        "launchplane-url: ${{ vars.LAUNCHPLANE_PUBLIC_URL }}",
        "route-path: /v1/drivers/generic-web/deploy",
        "generic-web-deploy",
        "deployment_record_id=result.deployment_record_id",
    )
    for fragment in required_fragments:
        assert fragment in workflow_text

    forbidden_fragments = (
        "source-ref-deploy",
        "generic-web-source-ref-deploy",
        "provider_source_ref",
        "context: $context",
        "launchplane-deploy/${TESTED_SHA}",
        "Remove transient Launchplane deploy ref",
        "--request DELETE",
        "contents: write",
    )
    for fragment in forbidden_fragments:
        assert fragment not in workflow_text


def test_launchplane_deploy_workflow_has_no_direct_dokploy_authority() -> None:
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    forbidden_fragments = (
        "DOKPLOY_",
        "dokploy-deploy",
        "compose.one",
        "compose.update",
        "compose.deploy",
        "x-api-key",
        "customGitBranch",
    )
    for fragment in forbidden_fragments:
        assert fragment not in workflow_text
