"""
Characterization tests — k8s/manifest.yaml required fields.

Pins the Doane K8s deployment standard's required fields so a future manifest
edit (templating, a copy-paste from another service, a well-meaning cleanup)
can't silently drop something load-bearing. These don't apply the manifest —
they only parse it and assert structure/values, so they're safe to run
anywhere (no cluster, no kubectl).

What each pins, and why it matters if it changes:
- Namespace 'prod' on every resource — a stray default namespace silently
  deploys nowhere near the real service.
- imagePullSecrets: regcred — missing this means ImagePullBackOff in prod.
- secretKeyRef name/key present for every secret-backed env var — the
  "indentation footgun" CLAUDE.md warns about (name/key must nest UNDER
  secretKeyRef, not sit beside it) would parse fine as YAML but bind nothing.
- Service port 80 + the Linkerd l5d-dst-override annotation matching it —
  a mismatch here means the mesh destination has no endpoints (silent 404
  even though the pod is healthy).
- Middleware named without a namespace prefix baked in, and the IngressRoute's
  reference matching it exactly — the doubled "prod-prod-" anti-pattern.
- TLS secretName / cert-manager ClusterIssuer consistency between the
  IngressRoute and the Certificate resource.
- Docker image name uses dots (Doane's registry doesn't handle hyphens) and
  is version-pinned (never :latest, so Argo can detect image changes).
- Liveness/readiness probes point at the split /api/v1/health(/deep) paths.
"""
from pathlib import Path

import yaml

_MANIFEST_PATH = Path(__file__).resolve().parents[2] / 'k8s' / 'manifest.yaml'


def _load_resources():
    with open(_MANIFEST_PATH) as fh:
        return list(yaml.safe_load_all(fh))


def _by_kind(resources, kind):
    return next(r for r in resources if r['kind'] == kind)


def test_manifest_parses_and_has_expected_resource_kinds_characterization():
    resources = _load_resources()
    kinds = [r['kind'] for r in resources]
    assert kinds == ['Deployment', 'Service', 'IngressRoute', 'Middleware', 'Certificate'], (
        'Resource kinds/order drifted from the known-good manifest shape.')


def test_namespace_is_prod_on_every_resource_characterization():
    for r in _load_resources():
        assert r['metadata']['namespace'] == 'prod', (
            f'{r["kind"]}/{r["metadata"]["name"]} is not in namespace "prod".')


def test_deployment_pull_secret_and_image_pin_characterization():
    dep = _by_kind(_load_resources(), 'Deployment')
    pod_spec = dep['spec']['template']['spec']
    pull_secrets = {s['name'] for s in pod_spec.get('imagePullSecrets', [])}
    assert 'regcred' in pull_secrets, 'imagePullSecrets must include regcred or the pod hits ImagePullBackOff.'

    image = pod_spec['containers'][0]['image']
    assert '-' not in image.split(':')[0].split('/')[-1], (
        f'Image name "{image}" uses a hyphen — Doane\'s Docker Hub org does not handle '
        'hyphens in image names (use dots instead).'
    )
    assert not image.endswith(':latest'), (
        'Image must be pinned to an explicit version tag, never :latest, so Argo can '
        'detect image changes.'
    )


def test_secretkeyref_indentation_characterization():
    # A parsed dict already proves the YAML is well-formed; this asserts the
    # *semantic* shape (name+key present under secretKeyRef) the "footgun"
    # CLAUDE.md warns about, not just that it parsed.
    dep = _by_kind(_load_resources(), 'Deployment')
    env = dep['spec']['template']['spec']['containers'][0]['env']
    secret_backed = [e for e in env if 'valueFrom' in e]
    assert secret_backed, 'Expected at least one secretKeyRef-backed env var.'
    for e in secret_backed:
        ref = e['valueFrom']['secretKeyRef']
        assert ref.get('name'), f'{e["name"]}: secretKeyRef missing "name".'
        assert ref.get('key'), f'{e["name"]}: secretKeyRef missing "key".'


def test_probes_target_split_health_endpoints_characterization():
    dep = _by_kind(_load_resources(), 'Deployment')
    container = dep['spec']['template']['spec']['containers'][0]
    assert container['livenessProbe']['httpGet']['path'] == '/api/v1/health'
    assert container['readinessProbe']['httpGet']['path'] == '/api/v1/health/deep'


def test_service_port_is_80_characterization():
    svc = _by_kind(_load_resources(), 'Service')
    ports = svc['spec']['ports']
    assert any(p['port'] == 80 for p in ports), 'Service port must be 80 (mesh/edge convention).'


def test_linkerd_annotation_matches_service_port_characterization():
    ing = _by_kind(_load_resources(), 'IngressRoute')
    svc = _by_kind(_load_resources(), 'Service')
    svc_name = svc['metadata']['name']
    ns = svc['metadata']['namespace']
    svc_port = next(p['port'] for p in svc['spec']['ports'])
    annotations = ing['metadata'].get('annotations', {})
    override = annotations.get('ingress.kubernetes.io/custom-request-headers', '')
    assert 'l5d-dst-override' in override, 'IngressRoute is missing the Linkerd l5d-dst-override annotation.'
    expected = f'l5d-dst-override:{svc_name}.{ns}.svc.cluster.local:{svc_port}'
    assert expected in override, (
        f'Linkerd override does not match the Service port ({svc_port}) — '
        f'expected "{expected}", got "{override}". A mismatch here means the mesh '
        'destination has no endpoints even though the pod is healthy.'
    )


def test_middleware_name_has_no_baked_in_namespace_prefix_characterization():
    mw = _by_kind(_load_resources(), 'Middleware')
    ns = mw['metadata']['namespace']
    name = mw['metadata']['name']
    assert not name.startswith(f'{ns}-'), (
        f'Middleware name "{name}" bakes the namespace into the name — Traefik already '
        f'qualifies cross-provider references as "<namespace>-<name>@kubernetescrd", so '
        f'this would resolve to a doubled "{ns}-{name}" reference.'
    )


def test_ingressroute_middleware_reference_matches_middleware_name_characterization():
    ing = _by_kind(_load_resources(), 'IngressRoute')
    mw = _by_kind(_load_resources(), 'Middleware')
    referenced = ing['spec']['routes'][0]['middlewares'][0]['name']
    assert referenced == mw['metadata']['name'], (
        'IngressRoute middlewares[].name must exactly match the Middleware resource\'s '
        'own metadata.name.'
    )


def test_tls_secret_and_cluster_issuer_consistency_characterization():
    ing = _by_kind(_load_resources(), 'IngressRoute')
    cert = _by_kind(_load_resources(), 'Certificate')
    assert ing['spec']['tls']['secretName'] == cert['spec']['secretName'] == 'wildcard-doane-tls'
    assert cert['spec']['issuerRef']['name'] == 'prod-letsencrypt'
    assert cert['spec']['issuerRef']['kind'] == 'ClusterIssuer'
