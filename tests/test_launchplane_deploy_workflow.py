from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "launchplane-deploy.yml"


def test_launchplane_deploy_workflow_uses_launchplane_source_ref_route() -> None:
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    required_fragments = (
        "name: Launchplane Deploy",
        "id-token: write",
        "cbusillo/launchplane/.github/actions/launchplane-request@main",
        "launchplane-url: ${{ vars.LAUNCHPLANE_PUBLIC_URL }}",
        "route-path: /v1/drivers/generic-web/source-ref-deploy",
        "generic-web-source-ref-deploy",
        "provider_source_ref: $providerSourceRef",
        "name: Remove transient Launchplane deploy ref",
        "--request DELETE",
    )
    for fragment in required_fragments:
        assert fragment in workflow_text


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
