#!/usr/bin/env bash
# The cross-node chat stage on ONE machine, against the LIVE mesh.
#
# Two nodes, each in its own container (its own network namespace, so both
# bind 8080/4242/4243), each claimed and announced by its own owner exactly as
# the wizard does, both reaching the live canonical over the internet. Then
# the same stage the five-platform gate runs (tools/qa_runner/cross_platform_chat.py)
# drives them through each agent's published port. Minutes per try instead of
# a 40-minute CI round trip; the emulator is not involved.
#
#   tools/qa_runner/local_mesh/run.sh [SERVER_PRERELEASE_TAG]
#
#   SERVER_PRERELEASE_TAG  CIRISServer prerelease whose manylinux wheel replaces
#                          the requirements.txt pin (e.g. test-0.5.241-0180f918).
#                          Empty = the pin.
# Environment:
#   MESH_OUT     where homes, logs, DBs and the report land (default: a new dir
#                under ${TMPDIR:-/tmp})
#   MESH_KEEP=1  leave both containers running afterwards (for poking at them)
#   RUST_LOG     passed to both nodes (e.g. info,ciris_edge::blob_swarm=debug)
#   MESH_REUSE=1 keep MESH_OUT's homes: restart the same two nodes, skip setup
#   MESH_LLM_KEY_FILE  the agents' LLM key, mounted read-only (default ~/.together_key)
#   MESH_LLM_MODEL / MESH_LLM_BASE_URL / MESH_LLM_PROVIDER  default Together gemma-4-31B-it
#
# Exit status is the stage's: 0 only when every enforced step passed.
set -uo pipefail

repo=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
tag="${1:-}"
out="${MESH_OUT:-$(mktemp -d "${TMPDIR:-/tmp}/ciris-local-mesh-XXXXXX")}"
mkdir -p "$out"
image="ciris-local-mesh:${tag:-pin}"
names=(mesh-a mesh-b)
ports=(18081 18082)

say() { printf '[local-mesh] %s\n' "$*"; }

key_file="${MESH_LLM_KEY_FILE:-$HOME/.together_key}"
[ -r "$key_file" ] || { say "no readable LLM key at $key_file (set MESH_LLM_KEY_FILE)"; exit 2; }

# ── Image: the committed tree (git archive), plus the prerelease wheel ───────
ctx=$(mktemp -d "${TMPDIR:-/tmp}/ciris-local-mesh-ctx-XXXXXX")
trap 'rm -rf "$ctx"' EXIT
git -C "$repo" archive HEAD | tar -x -C "$ctx"
mkdir -p "$ctx/serverwheel"
if [ -n "$tag" ]; then
  gh release download "$tag" --repo CIRISAI/CIRISServer --pattern 'ciris_server-*manylinux*x86_64.whl' \
    --dir "$ctx/serverwheel" || { say "no manylinux x86_64 wheel on $tag"; exit 2; }
  say "server prerelease: $(ls "$ctx/serverwheel")"
fi
say "building $image from $(git -C "$repo" rev-parse --short HEAD)"
docker build -q -t "$image" -f "$ctx/tools/qa_runner/local_mesh/Dockerfile" "$ctx" >/dev/null \
  || { say "image build failed"; exit 2; }

# ── Two nodes ────────────────────────────────────────────────────────────────
for i in 0 1; do
  n=${names[$i]}
  docker rm -f "ciris-$n" >/dev/null 2>&1
  [ "${MESH_REUSE:-0}" = 1 ] || rm -rf "${out:?}/$n"
  mkdir -p "$out/$n"
  rm -f "$out/$n/mesh_failed.txt" "$out/$n/mesh_restarted.txt"
  docker run -d --name "ciris-$n" --user "$(id -u):$(id -g)" \
    -e HOME=/mesh/home -e CIRIS_HOME=/mesh/home/ciris -e MESH_LABEL="qa-node-$(date +%s)$i" \
    -e RUST_LOG="${RUST_LOG:-}" -v "$key_file:/run/mesh/llm_key:ro" \
    -e MESH_LLM_MODEL="${MESH_LLM_MODEL:-google/gemma-4-31B-it}" \
    -e MESH_LLM_BASE_URL="${MESH_LLM_BASE_URL:-https://api.together.xyz/v1}" \
    -e MESH_LLM_PROVIDER="${MESH_LLM_PROVIDER:-openai}" \
    -v "$out/$n:/mesh/home" -p "127.0.0.1:${ports[$i]}:8080" "$image" >/dev/null \
    || { say "could not start $n"; exit 2; }
  say "$n up on :${ports[$i]} (home $out/$n)"
done

# Ready = the bootstrap's marker (fresh) or its restart note (reuse).
for i in 0 1; do
  n=${names[$i]}; home="$out/$n/ciris"; deadline=$((SECONDS + 600))
  until [ -f "$home/mesh_ready.json" ] && { [ "${MESH_REUSE:-0}" != 1 ] || [ -f "$home/mesh_restarted.txt" ]; }; do
    if [ -f "$home/mesh_failed.txt" ] || [ "$(docker inspect -f '{{.State.Running}}' "ciris-$n" 2>/dev/null)" != true ]; then
      say "$n failed to come up: $(cat "$home/mesh_failed.txt" 2>/dev/null)"; docker logs --tail 40 "ciris-$n"; exit 2
    fi
    [ $SECONDS -lt $deadline ] || { say "$n not ready within 600s"; docker logs --tail 40 "ciris-$n"; exit 2; }
    sleep 3
  done
  say "$n ready: $(tr -d '\n ' < "$home/mesh_ready.json" | cut -c1-200)"
done

# A fresh node is restarted from its own home before the stage, as the gate
# restarts the linux backend: same owner, same fedID, same keys, NOT first run.
# It also keeps the stage clear of the in-process first-run resume, which can
# end the API adapter when setup completes during the agent's own startup.
if [ "${MESH_REUSE:-0}" != 1 ]; then
  for n in "${names[@]}"; do
    rm -f "$out/$n/ciris/mesh_restarted.txt"
    docker restart -t 30 "ciris-$n" >/dev/null || { say "could not restart $n"; exit 2; }
  done
  for n in "${names[@]}"; do
    deadline=$((SECONDS + 300))
    until [ -f "$out/$n/ciris/mesh_restarted.txt" ]; do
      [ "$(docker inspect -f '{{.State.Running}}' "ciris-$n" 2>/dev/null)" = true ] \
        || { say "$n died on restart"; docker logs --tail 40 "ciris-$n"; exit 2; }
      [ $SECONDS -lt $deadline ] || { say "$n not back within 300s"; docker logs --tail 40 "ciris-$n"; exit 2; }
      sleep 3
    done
    say "$n restarted from its home"
  done
fi

# ── The stage ────────────────────────────────────────────────────────────────
rc=0
( cd "$repo" && python3 -m tools.qa_runner.cross_platform_chat run \
    --node "${names[0]}=http://127.0.0.1:${ports[0]}" --node "${names[1]}=http://127.0.0.1:${ports[1]}" \
    --username qaadmin --password qa_test_password_12345 --out "$out/result.json" ) || rc=$?

for n in "${names[@]}"; do docker logs "ciris-$n" > "$out/$n/container.log" 2>&1; done
if [ "$rc" != 0 ]; then
  ( cd "$repo" && python3 -m tools.qa_runner.cross_platform_chat scan \
      --logs "${names[0]}=$out/${names[0]}/ciris/logs" --logs "${names[1]}=$out/${names[1]}/ciris/logs" \
      --out "$out/scan.txt" )
fi
if [ "${MESH_KEEP:-0}" != 1 ]; then
  for n in "${names[@]}"; do docker stop -t 30 "ciris-$n" >/dev/null 2>&1; docker rm "ciris-$n" >/dev/null 2>&1; done
fi
say "stage exit $rc; report $out/result.json; homes, logs and DBs under $out"
exit "$rc"
