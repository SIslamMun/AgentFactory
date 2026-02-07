FROM iowarp/iowarp:latest

USER root

# Install Python dependencies and build tools for cte_helper
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        cmake pkg-config libelf-dev libyaml-cpp-dev libopenmpi-dev \
        libcereal-dev libboost-all-dev libpgm-dev libxml2-dev \
        libzmq3-dev libnorm-dev libsodium-dev && \
    pip3 install --no-cache-dir --break-system-packages pyzmq pydantic && \
    rm -rf /var/lib/apt/lists/*

# Build cte_helper (C++ bridge to CTE, bypasses broken nanobind extension)
COPY cte_helper.cpp CMakeLists.txt /tmp/cte_build/
RUN cd /tmp/cte_build && \
    mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release && \
    make -j$(nproc) && \
    cp cte_helper /usr/local/bin/cte_helper && \
    rm -rf /tmp/cte_build

COPY bridge.py /opt/agent-factory/bridge.py
COPY wrp_cee.py /opt/agent-factory/wrp_cee.py
COPY wrp_conf.yaml /etc/iowarp/wrp_conf.yaml

ENV PYTHONPATH=/opt/agent-factory:$PYTHONPATH
ENV WRP_RUNTIME_CONF=/etc/iowarp/wrp_conf.yaml

CMD ["sh", "-c", "chimaera_start_runtime & sleep 5 && python3 /opt/agent-factory/bridge.py"]
