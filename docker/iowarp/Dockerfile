FROM iowarp/iowarp:latest

RUN pip3 install --no-cache-dir --break-system-packages pyzmq pydantic

COPY bridge.py /opt/agent-factory/bridge.py
COPY wrp_cee.py /opt/agent-factory/wrp_cee.py
COPY wrp_conf.yaml /etc/iowarp/wrp_conf.yaml

ENV PYTHONPATH=/opt/agent-factory:$PYTHONPATH

CMD ["sh", "-c", "chimaera_start_runtime & sleep 3 && python3 /opt/agent-factory/bridge.py"]
