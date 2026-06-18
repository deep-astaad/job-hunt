# Homelab Deploy Copy

These files mirror the canonical Jobhunt deployment files in `/home/neovara/homelab/jobhunt`.

They are kept in this project for bookkeeping and review alongside application changes. Jenkins does not apply these files directly; production deployment still uses the homelab repo convention:

```bash
cd /home/neovara/homelab
make config-jobhunt
make up-jobhunt
```

## Architecture

Traffic flows: **Browser → Traefik → frontend (Next.js :3000)** for all routes, except `/admin/*` which routes directly to **Django :8000**. The Next.js BFF proxy calls Django on the internal Docker network (`http://django:8000`), bypassing Traefik and any auth middleware entirely.

No Authelia middleware is applied to either service — auth is handled by Django sessions.

## First-time setup / after compose changes

Jenkins builds and pushes both `job-hunt` (backend) and `job-hunt-frontend` (Next.js) images on every `main` merge. After a push that changes the compose or app.env:

```bash
# on the homelab
cd /home/neovara/homelab
make config-jobhunt   # syncs compose + env from this repo's deploy/homelab/
make up-jobhunt       # docker compose pull && up -d
```

## Creating the first admin user

```bash
docker exec -it jobhunt-django python backend/manage.py createsuperuser
```

Use those credentials in the in-app login page.
