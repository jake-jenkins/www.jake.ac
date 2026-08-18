# Deploying to k3s with Flux

This follows the `gbe-api` deployment loop without replacing that repository as
the cluster's existing Flux source of truth:

1. A push to `main` publishes `ghcr.io/jake-jenkins/www.jake.ac:main-<run-number>`.
2. Flux scans those immutable tags and commits the selected tag to
   `kubernetes/deployment.yaml`.
3. Flux reconciles the Kustomize manifests onto k3s.

## One-time setup

The repository needs a write-capable SSH deploy key so Flux can read it and
commit image updates. Store that key in `flux-system` as `jakeac-git`, then add
the public half as a read/write deploy key on the GitHub repository.

```bash
ssh-keygen -t ed25519 -N '' -C flux-jakeac -f /tmp/flux-jakeac
flux create secret git jakeac-git \
  --namespace=flux-system \
  --url=ssh://git@github.com/jake-jenkins/www.jake.ac \
  --private-key-file=/tmp/flux-jakeac
```

Add `/tmp/flux-jakeac.pub` at **GitHub → repository Settings → Deploy keys**
with write access, then securely remove both temporary key files.

The existing private GHCR pull credential also needs to be copied into the app
namespace. Secret values are never stored in Git:

```bash
kubectl apply -f kubernetes/namespace.yaml

kubectl -n default get secret ghcr-pull-secret -o json |
  jq 'del(.metadata.namespace, .metadata.resourceVersion, .metadata.uid,
    .metadata.creationTimestamp, .metadata.managedFields) |
    .metadata.namespace="jakeac"' |
  kubectl apply -f -
```

Flux already has `flux-system/ghcr-pull-secret` for image scanning. Apply the
separate app source after `jakeac-git` exists:

```bash
kubectl apply -f clusters/k3s/jakeac.yaml
flux reconcile source git jakeac
flux reconcile kustomization jakeac --with-source
```

For fully declarative ownership, also commit `clusters/k3s/jakeac.yaml` into
the existing cluster source repository (`gbe-api`) under `clusters/k3s/`.

## TLS and DNS

Create a Cloudflare origin certificate covering `www.jake.ac`, and store it in
the app namespace:

```bash
kubectl -n jakeac create secret tls cloudflare-origin-cert-jake-ac \
  --cert=origin.pem \
  --key=origin-key.pem
```

Point/proxy `www.jake.ac` to the k3s Traefik load balancer, then verify:

```bash
flux get images all -A
kubectl -n jakeac rollout status deployment/jakeac --timeout=5m
curl -I https://www.jake.ac
```
