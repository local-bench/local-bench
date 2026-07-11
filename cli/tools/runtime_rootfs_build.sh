#!/bin/bash
set -euo pipefail
umask 022
export SOURCE_DATE_EPOCH=0 TZ=UTC LC_ALL=C.UTF-8
if ! command -v sudo >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then
  sudo() { "$@"; }
fi

test "$(tar --version | head -n 1)" = "tar (GNU tar) 1.35"
test "$(xz --version | head -n 1)" = "xz (XZ Utils) 5.4.5"
test "$(python3 --version)" = "Python 3.12.3"

config=$1
output=$2
work=$(mktemp -d)
case "$work" in
  /tmp/tmp.*) ;;
  *) echo "unsafe temporary build path: $work" >&2; exit 2 ;;
esac
cleanup() {
  case "$work" in
    /tmp/tmp.*) sudo rm -rf -- "$work" ;;
    *) echo "refusing unsafe cleanup path: $work" >&2 ;;
  esac
}
trap cleanup EXIT

get() {
  python3 -c 'import json,sys; value=json.loads(sys.argv[1]);
for part in sys.argv[2].split("."): value=value[part]
print(value)' "$config" "$1"
}

base_url=$(get base.url)
base_sha=$(get base.sha256)
runtime_id=$(get runtime_id)
wheel=$(get worker_wheel_wsl_path)
wheel_name=$(basename "$wheel")
wheel_sha=$(get worker.sha256)
lock=$(get dependency_lock_wsl_path)
lock_sha=$(get dependency_lock_sha256)
wheelhouse=$(get wheelhouse_wsl_path)
wheelhouse_sha=$(get wheelhouse_sha256)
snapshot=$(get apt_snapshot.url)
indexes_sha=$(get apt_snapshot.indexes_sha256)
root="$work/rootfs"
mkdir -p "$root"

curl --fail --location --proto '=https' --tlsv1.2 "$base_url" -o "$work/base.tar.xz"
printf '%s  %s\n' "$base_sha" "$work/base.tar.xz" | sha256sum --check --status
sudo tar --numeric-owner --xattrs --acls -xJf "$work/base.tar.xz" -C "$root"
sudo cp --remove-destination /etc/resolv.conf "$root/etc/resolv.conf"
python3 -c 'import json,sys; c=json.loads(sys.argv[1]); print("\n".join("deb [check-valid-until=no] {} {} main universe".format(c["apt_snapshot"]["url"], suite) for suite in c["apt_snapshot"]["suites"]))' "$config" | sudo tee "$root/etc/apt/sources.list" >/dev/null
sudo rm -f "$root/etc/apt/sources.list.d"/*
sudo chroot "$root" /usr/bin/env DEBIAN_FRONTEND=noninteractive apt-get update
actual_indexes=$(sudo chroot "$root" /bin/sh -c "find /var/lib/apt/lists -type f -print0 | sort -z | xargs -0 sha256sum" | sha256sum | cut -d' ' -f1)
if [ "$actual_indexes" != "$indexes_sha" ]; then
  printf 'apt index digest mismatch: expected=%s actual=%s\n' "$indexes_sha" "$actual_indexes" >&2
  exit 3
fi
mapfile -t packages < <(python3 -c 'import json,sys; print("\n".join(json.loads(sys.argv[1])["apt_packages"]))' "$config")
sudo chroot "$root" /usr/bin/env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${packages[@]}"
sudo chroot "$root" apt-mark hold "${packages[@]%%=*}"
sudo chroot "$root" useradd --no-log-init --create-home --uid 10001 --user-group --shell /bin/sh lbworker
sudo chroot "$root" passwd --lock root
sudo chroot "$root" passwd --lock lbworker
sudo rm -f "$root/usr/bin/sudo" "$root/usr/bin/su"

printf '%s  %s\n' "$wheel_sha" "$wheel" | sha256sum --check --status
printf '%s  %s\n' "$lock_sha" "$lock" | sha256sum --check --status
actual_wheelhouse=$(cd "$wheelhouse" && find . -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)
test "$actual_wheelhouse" = "$wheelhouse_sha"
sudo mkdir -p "$root/opt/localbench/wheelhouse" "$root/opt/localbench/bin"
sudo cp "$wheelhouse"/* "$root/opt/localbench/wheelhouse/"
sudo cp "$lock" "$root/opt/localbench/requirements.lock"
sudo cp "$wheel" "$root/opt/localbench/$wheel_name"
sudo chroot "$root" python3 -m venv /opt/localbench/venv
sudo chroot "$root" /opt/localbench/venv/bin/pip install --no-index --require-hashes --find-links /opt/localbench/wheelhouse -r /opt/localbench/requirements.lock
sudo chroot "$root" /opt/localbench/venv/bin/pip install --no-index --no-deps "/opt/localbench/$wheel_name"
sudo rm -rf "$root/opt/localbench/wheelhouse" "$root/opt/localbench/requirements.lock" "$root/opt/localbench/$wheel_name"
sudo mkdir -p "$root/home/lbworker/appworld"
sudo chown -R 10001:10001 "$root/opt/localbench/venv" "$root/home/lbworker/appworld"

sudo tee "$root/opt/localbench/bin/localbench-worker" >/dev/null <<'EOF'
#!/bin/sh
exec /opt/localbench/venv/bin/python -m localbench.appliance.worker "$@"
EOF
sudo tee "$root/opt/localbench/bin/provision-appworld" >/dev/null <<'EOF'
#!/bin/sh
exec /opt/localbench/venv/bin/python -m localbench.appliance.worker provision "$1"
EOF
sudo chmod 0755 "$root/opt/localbench/bin/localbench-worker" "$root/opt/localbench/bin/provision-appworld"
printf '%s' '[automount]
enabled=false
mountFsTab=false

[interop]
enabled=false
appendWindowsPath=false

[user]
default=lbworker
' | sudo tee "$root/etc/wsl.conf" >/dev/null
python3 -c 'import json,sys; print(json.dumps({"owner":"localbench","runtime_id":sys.argv[1],"schema":"localbench.appliance_owner.v1"},sort_keys=True,separators=(",",":")))' "$runtime_id" | sudo tee "$root/etc/localbench-appliance-owner.json" >/dev/null
sudo chmod 0644 "$root/etc/wsl.conf" "$root/etc/localbench-appliance-owner.json"
python_version=$(sudo chroot "$root" /usr/bin/python3 --version | sed 's/^Python //')
bwrap_version=$(sudo chroot "$root" /usr/bin/bwrap --version | sed 's/^bubblewrap //')
sudo mkdir -p "$root/usr/share/localbench"
printf '{"bubblewrap_version":"%s","python_version":"%s"}\n' "$bwrap_version" "$python_version" | sudo tee "$root/usr/share/localbench/build-metadata.json" >/dev/null
sudo chmod 0644 "$root/usr/share/localbench/build-metadata.json"

sudo find "$root/etc/systemd/system" -type l -delete 2>/dev/null || true
sudo rm -rf "$root/var/lib/apt/lists"/* "$root/var/cache/apt"/* "$root/var/log"/* "$root/tmp"/*
sudo find "$root" -xdev -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
sudo find "$root" -xdev -type d -name __pycache__ -empty -delete
sudo rm -f "$root/etc/machine-id" "$root/var/lib/dbus/machine-id" "$root/etc/resolv.conf"
sudo touch -d @0 "$root/etc/machine-id"
sudo sed -i -E 's/^([^:]+:[^:]*):[0-9]+:/\1:0:/' "$root/etc/shadow" "$root/etc/gshadow"
sudo find "$root" -xdev -type d -exec chmod u=rwx,go=rx {} +
# Preserve the executable class before normalizing regular-file modes.  This
# includes ELF interpreters under /usr/lib; stripping their execute bit makes
# an otherwise valid imported WSL rootfs unable to launch any dynamic binary.
sudo find "$root" -xdev -type f -perm /111 -exec chmod u=rwx,go=rx {} +
sudo find "$root" -xdev -type f ! -perm /111 -exec chmod u=rw,go=r {} +
sudo find "$root" -xdev -exec touch -h -d @0 {} +
sudo chown -R 0:0 "$root"
sudo chown -R 10001:10001 "$root/home/lbworker" "$root/opt/localbench/venv"
sudo tar --sort=name --format=posix --pax-option=delete=atime,delete=ctime --numeric-owner --mtime=@0 --clamp-mtime --no-xattrs --no-acls --no-selinux -C "$root" -cf "$work/rootfs.tar" .
xz --threads=1 --check=crc64 -9e --stdout "$work/rootfs.tar" > "$output"
