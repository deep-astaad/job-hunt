# Homelab Deploy Copy

These files mirror the canonical Jobhunt deployment files in `/home/neovara/homelab/jobhunt`.

They are kept in this project for bookkeeping and review alongside application changes. Jenkins does not apply these files directly; production deployment still uses the homelab repo convention:

```bash
cd /home/neovara/homelab
make config-jobhunt
make up-jobhunt
```
