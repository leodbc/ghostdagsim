ARG NS3_VERSION=3.46.1
ARG GHOSTDAGSIM_DIAGNOSTICS=OFF
ARG GHOSTDAGSIM_CPU_PROFILER=OFF

FROM debian:bookworm-slim AS builder

ARG NS3_VERSION
ARG GHOSTDAGSIM_DIAGNOSTICS

RUN case "$GHOSTDAGSIM_DIAGNOSTICS" in ON|OFF) ;; *) echo "GHOSTDAGSIM_DIAGNOSTICS must be ON or OFF" >&2; exit 2 ;; esac

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake g++ python3 \
    libopenmpi-dev openmpi-bin \
    wget git bzip2 ca-certificates tar && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN wget -q https://www.nsnam.org/release/ns-allinone-${NS3_VERSION}.tar.bz2 && \
    tar xjf ns-allinone-${NS3_VERSION}.tar.bz2 && \
    rm ns-allinone-${NS3_VERSION}.tar.bz2

WORKDIR /opt/ns-allinone-${NS3_VERSION}/ns-${NS3_VERSION}

# Preserve the canonical Phase 2 MPI buffer repair.
RUN sed -i 's/^const uint32_t MAX_MPI_MSG_SIZE = 2000;/const uint32_t MAX_MPI_MSG_SIZE = 2097152;/' \
        src/mpi/model/granted-time-window-mpi-interface.h && \
    sed -i 's/^const uint32_t NULL_MESSAGE_MAX_MPI_MSG_SIZE = 2000;/const uint32_t NULL_MESSAGE_MAX_MPI_MSG_SIZE = 2097152;/' \
        src/mpi/model/null-message-mpi-interface.cc && \
    grep -q 'MAX_MPI_MSG_SIZE = 2097152' src/mpi/model/granted-time-window-mpi-interface.h

# The optimized ns-3 profile enables native optimizations by default. Re-run
# CMake with NS3_NATIVE_OPTIMIZATIONS=OFF before compiling so the benchmark
# image does not inherit the build runner's CPU ISA.
RUN ./ns3 configure \
        --build-profile=optimized \
        --enable-modules=core,network,internet,point-to-point \
        --enable-mpi \
        -- -DGHOSTDAGSIM_METRICS:BOOL=ON \
           -DGHOSTDAGSIM_DIAGNOSTICS:BOOL=${GHOSTDAGSIM_DIAGNOSTICS} && \
    cmake -S . -B cmake-cache \
        -DNS3_NATIVE_OPTIMIZATIONS:BOOL=OFF \
        -DGHOSTDAGSIM_METRICS:BOOL=ON \
        -DGHOSTDAGSIM_DIAGNOSTICS:BOOL=${GHOSTDAGSIM_DIAGNOSTICS} && \
    grep -q '^NS3_NATIVE_OPTIMIZATIONS:BOOL=OFF$' cmake-cache/CMakeCache.txt && \
    grep -q '^GHOSTDAGSIM_METRICS:BOOL=ON$' cmake-cache/CMakeCache.txt && \
    grep -q "^GHOSTDAGSIM_DIAGNOSTICS:BOOL=${GHOSTDAGSIM_DIAGNOSTICS}$" cmake-cache/CMakeCache.txt && \
    ./ns3 build

# The Docker build context is an exact checkout of the canonical simulator SHA.
# With native optimizations disabled, ns-3 emits the release executable without
# the "-optimized" suffix. Normalize that verified build output to a stable
# builder-stage path so the runtime stage does not depend on profile suffixes.
COPY . /opt/ns-allinone-${NS3_VERSION}/ns-${NS3_VERSION}/scratch/ghostdagsim/
RUN ./ns3 build ghostdagsim && \
    grep -q '^NS3_NATIVE_OPTIMIZATIONS:BOOL=OFF$' cmake-cache/CMakeCache.txt && \
    grep -q '^GHOSTDAGSIM_METRICS:BOOL=ON$' cmake-cache/CMakeCache.txt && \
    grep -q "^GHOSTDAGSIM_DIAGNOSTICS:BOOL=${GHOSTDAGSIM_DIAGNOSTICS}$" cmake-cache/CMakeCache.txt && \
    test -x "build/scratch/ghostdagsim/ns${NS3_VERSION}-ghostdagsim" && \
    install -m 0755 \
      "build/scratch/ghostdagsim/ns${NS3_VERSION}-ghostdagsim" \
      /opt/ghostdagsim-portable

FROM debian:bookworm-slim

ARG NS3_VERSION
ARG GHOSTDAGSIM_DIAGNOSTICS
ARG GHOSTDAGSIM_CPU_PROFILER

RUN case "$GHOSTDAGSIM_CPU_PROFILER" in ON|OFF) ;; *) echo "GHOSTDAGSIM_CPU_PROFILER must be ON or OFF" >&2; exit 2 ;; esac

LABEL org.opencontainers.image.title="ghostdagsim portable benchmark" \
      org.opencontainers.image.description="Portable x86_64 GHOSTDAG benchmark image (ns-3 + MPI)" \
      org.opencontainers.image.source="https://github.com/leodbc/ghostdagsim" \
      org.opencontainers.image.licenses="GPL-2.0" \
      io.ghostdagsim.ns3.native_optimizations="off" \
      io.ghostdagsim.ns3.version="${NS3_VERSION}" \
      io.ghostdagsim.ns3.build_profile="optimized" \
      io.ghostdagsim.metrics="on" \
      io.ghostdagsim.diagnostics="${GHOSTDAGSIM_DIAGNOSTICS}" \
      io.ghostdagsim.cpu_profiler="${GHOSTDAGSIM_CPU_PROFILER}"

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      libopenmpi-dev openmpi-bin \
      openssh-server openssh-client; \
    if [ "$GHOSTDAGSIM_CPU_PROFILER" = "ON" ]; then \
      apt-get install -y --no-install-recommends google-perftools binutils; \
    fi; \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p /root/.ssh /var/run/sshd && \
    chmod 700 /root/.ssh && \
    echo "PermitRootLogin yes" >> /etc/ssh/sshd_config && \
    echo "StrictHostKeyChecking no" > /root/.ssh/config && \
    echo "UserKnownHostsFile /dev/null" >> /root/.ssh/config

COPY --from=builder /opt/ghostdagsim-portable /usr/local/bin/ghostdagsim

RUN if [ "$GHOSTDAGSIM_CPU_PROFILER" = "ON" ]; then \
      command -v google-pprof >/dev/null; \
      ldconfig -p | grep -q 'libprofiler.so.0'; \
      nm -C /usr/local/bin/ghostdagsim | grep -q 'GhostDagNode::'; \
    fi

COPY --from=builder \
    /opt/ns-allinone-${NS3_VERSION}/ns-${NS3_VERSION}/build/lib/ \
    /usr/local/lib/ns3/

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY scripts/profile-rank.sh /usr/local/bin/profile-rank.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/profile-rank.sh

ENV LD_LIBRARY_PATH=/usr/local/lib/ns3
ENV MPI_THREADS=1

WORKDIR /results

EXPOSE 22

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
