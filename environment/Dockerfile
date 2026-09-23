FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates ffmpeg libglib2.0-0 libgl1 util-linux && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements/local-common.txt /tmp/common.txt
RUN pip install --no-cache-dir torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128 && pip install --no-cache-dir -r /tmp/common.txt && pip check
COPY harness /opt/afda/harness
COPY environment/run_offline.py /opt/afda/run_offline.py
ENV PYTHONPATH=/opt/afda HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
WORKDIR /submission
ENTRYPOINT ["python", "/opt/afda/run_offline.py"]
