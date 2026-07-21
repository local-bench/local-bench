# Coding sandbox: Windows CLI with a Docker engine in WSL2

Use this setup when `localbench` runs on Windows but the Docker daemon runs inside a WSL2
distribution. Docker Desktop is not required.

## 1. Use the rootful image store

Rootless and rootful Docker daemons have separate image stores. A normal in-distro `docker pull`
may talk to the rootless daemon and put the coding image in a store that a Windows client connected
to the rootful TCP daemon cannot see. Inspect and pull through the same rootful daemon that the
Windows client will use:

```bash
sudo docker image inspect <digest-pinned-image>
sudo docker pull <digest-pinned-image>
```

If `docker context show`, `DOCKER_HOST`, or the socket changes between those commands and the
benchmark, you may be talking to a different daemon and therefore a different image store.

## 2. Expose the daemon on the WSL adapter, not localhost

TCP port 2375 is unencrypted and grants root-equivalent control of the daemon. Use it only on the
host-internal WSL2 NAT network. Do not expose it through a Windows port proxy, a LAN interface,
mirrored networking, or an untrusted network.

Configure the rootful daemon to retain its Unix socket and listen on the WSL adapter:

```json
{
  "hosts": ["unix:///var/run/docker.sock", "tcp://0.0.0.0:2375"]
}
```

Save that as `/etc/docker/daemon.json`. On systemd distributions whose Docker unit already passes
`-H fd://`, clear that command-line host setting so it does not conflict with `daemon.json`:

```ini
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd
```

Apply it with `sudo systemctl edit docker.service`, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart docker
sudo ss -ltnp | grep 2375
```

From PowerShell, obtain the current WSL adapter address and use it for this session:

```powershell
wsl.exe -d <Distro> hostname -I
$env:DOCKER_HOST = "tcp://<WSL-adapter-IP>:2375"
docker version
```

Never set `DOCKER_HOST` to `tcp://localhost:2375` or `tcp://127.0.0.1:2375` for this topology. The
WSL2 localhost relay can pass ordinary daemon requests while dropping Docker attach output, which
makes a successful sandbox probe appear to return no data. The WSL adapter IP avoids that relay.
The adapter IP can change after WSL restarts, so resolve it again for each benchmark session.

## 3. Keep WSL alive and make detached work reapable

WSL2 may terminate an idle distribution. Keep a real Linux process alive in a separate terminal for
the duration of the benchmark:

```powershell
wsl.exe -d <Distro> --exec sleep infinity
```

Stop that foreground command after the run. Do not rely on `nohup ... &` launched by a short-lived
`wsl.exe` call: WSL may reap it when the initiating session exits. For detached helpers, use a named
transient systemd unit so the process has an explicit lifecycle and descendants are reaped together:

```bash
sudo systemd-run --unit=localbench-keepalive --collect /usr/bin/sleep infinity
sudo systemctl stop localbench-keepalive.service
```

Use the same transient-unit pattern for any other detached per-run helper, and stop its unit during
cleanup instead of searching for processes by name.

## 4. Use a version-matched static Windows client

Only the Docker client is needed on Windows. Check the engine version inside WSL:

```bash
sudo docker version --format '{{.Server.Version}}'
```

Download the matching Windows x86_64 static client archive from
`https://download.docker.com/win/static/stable/x86_64/docker-<version>.zip`, extract `docker.exe`,
and place its directory on the Windows `PATH`. Matching the client to the engine avoids API-version
surprises; `docker version` should show both client and server before starting `localbench`.

## Preflight checklist

- `DOCKER_HOST` uses the current WSL adapter IP, not localhost.
- `docker version` from Windows reports the intended rootful WSL daemon.
- `docker image inspect <digest-pinned-image>` succeeds from the Windows client.
- A keepalive process or transient unit remains active for the whole run.
- Port 2375 is confined to the host-internal WSL NAT network.
