#!/bin/sh
set -eu

if [ "${GHOSTDAGSIM_CPU_PROFILE:-0}" != "1" ]; then
  exec /usr/local/bin/ghostdagsim "$@"
fi

: "${OMPI_COMM_WORLD_RANK:?OMPI_COMM_WORLD_RANK is required for CPU profiling}"
: "${GHOSTDAGSIM_CPU_PROFILE_ROOT:?GHOSTDAGSIM_CPU_PROFILE_ROOT is required}"

rank="${OMPI_COMM_WORLD_RANK}"
frequency="${GHOSTDAGSIM_CPU_PROFILE_FREQUENCY:-100}"
signal="${GHOSTDAGSIM_CPU_PROFILE_SIGNAL:-12}"

case "$rank" in
  0|1|2|3) ;;
  *) echo "unexpected MPI rank for Gate-B CPU profile: $rank" >&2; exit 2 ;;
esac
case "$frequency" in
  100) ;;
  *) echo "unexpected CPU profile frequency: $frequency" >&2; exit 2 ;;
esac
case "$signal" in
  12) ;;
  *) echo "unexpected CPU profile signal: $signal" >&2; exit 2 ;;
esac

rank_dir="${GHOSTDAGSIM_CPU_PROFILE_ROOT}/rank${rank}"
mkdir -p "$rank_dir"

libprofiler="$(ldconfig -p | awk '/libprofiler\.so\.0/{print $NF; exit}')"
if [ -z "$libprofiler" ] || [ ! -r "$libprofiler" ]; then
  echo "libprofiler.so.0 not found" >&2
  exit 127
fi

printf '%s\n' "$$" > "$rank_dir/rank.pid"
cat > "$rank_dir/profile-context.json" <<EOF
{
  "rank": ${rank},
  "frequency_hz": ${frequency},
  "control_signal": ${signal},
  "profiler": "gperftools",
  "raw_profile_prefix": "cpu.prof"
}
EOF

export CPUPROFILE="$rank_dir/cpu.prof"
export CPUPROFILE_FREQUENCY="$frequency"
export CPUPROFILESIGNAL="$signal"
export LD_PRELOAD="${libprofiler}${LD_PRELOAD:+:${LD_PRELOAD}}"

exec /usr/local/bin/ghostdagsim "$@"
