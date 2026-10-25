# Jake.ac on the shared website VPS

Main address: https://www.jake.ac. HTTPS and HTTP requests for jake.ac redirect to the www address, preserving the path and query.

GitHub Actions builds and scans the immutable GHCR image. When repository variable `JAKE_DEPLOY_ENABLED` is exactly `true`, it writes a deployment manifest to `production-deploy`. Set `JAKE_ORIGIN_IP=185.132.39.23` to verify the replacement server before DNS cutover, preserving Host, TLS SNI and certificate validation.

The root-owned host agent polls the manifest using a dedicated read-only deploy key. It validates the registry prefix and digest, starts the inactive container, checks the homepage and favicon, tests Nginx and reloads it gracefully. It verifies the release through Nginx before recording state; failures restore the previous route. The previous container remains available for draining and rollback. Both deployment workflows share a concurrency group.

## Host installation

- Trusted scripts: `/usr/local/lib/jake-deploy/deploy.py`; install reviewed changes explicitly. The agent never runs downloaded repository code.
- State and read-only key: `/var/lib/jake-deploy`; key in `ssh/id_ed25519`, with pinned GitHub host key in `ssh/known_hosts`.
- Slots: `jake-blue` on 127.0.0.1:18201 and `jake-green` on 127.0.0.1:18202, container port 8080.
- Nginx site: `/etc/nginx/conf.d/jake-site.conf`, from `deploy/nginx-site.conf`.
- Agent-managed route fragment: `/etc/nginx/jake-routes.conf`, outside conf.d; initially `location / { return 503; }`.
- Loopback verification listener: 127.0.0.1:18444. Do not expose it or container ports in the firewall.
- Shared Nginx lock: `/var/lib/website-deploy/nginx.lock`, also used by GB Energy.
- Certificate: `/etc/letsencrypt/live/jake.ac`, covering jake.ac and www.jake.ac, issued by Cloudflare DNS validation. The root-only API credentials stay on the VPS. The shared Certbot renewal hook tests and reloads Nginx.
- Install `jake-deploy.service` and `jake-deploy.timer` under `/etc/systemd/system`, reload systemd, and enable the timer after credentials and initial HTTPS checks pass.

Containers run as UID/GID 101, read-only with all capabilities dropped, no-new-privileges, 32 MiB temporary storage, 96 MiB RAM, 0.5 CPU and rotated logs. No application data volume or Node runtime is needed: Astro builds in CI and the runtime image serves static files.

## Operations

```sh
systemctl status jake-deploy.timer
journalctl -u jake-deploy.service -n 100
cat /var/lib/jake-deploy/state.json
curl --resolve www.jake.ac:443:185.132.39.23 https://www.jake.ac/__deployment
```

The **Rollback production** workflow accepts a retained published image digest and its full source commit. It updates the desired manifest and uses the same verified deployment path. Preserve rollback images in GHCR. Pause automatic updates with `systemctl stop jake-deploy.timer`.

Before DNS cutover, verify a release and rollback, the main page and assets, both HTTPS hostnames and the apex redirect. Update only the website A/AAAA/CNAME records; retain mail and verification records. The current IONOS host has no configured global IPv6 address, so do not create an AAAA record until IPv6 is configured and tested.

Blue/green covers application releases, not VPS failures. Cache-busted assets should stay available long enough for browsers holding an earlier HTML page; retained containers alone do not provide cross-release asset routing.
